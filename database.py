"""
SQLite database layer for YouTube automation.
Tracks: video history, API costs, performance metrics.
Zero config — creates yt_automation.db automatically.
"""
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime

from config import DB_PATH


@contextmanager
def _conn():
    """Context manager that auto-closes the connection even if an exception occurs."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_conn():
    """Legacy helper — prefer using `with _conn() as conn:` instead."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS videos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic       TEXT NOT NULL,
                title       TEXT,
                youtube_id  TEXT UNIQUE,
                status      TEXT DEFAULT 'pending',
                niche       TEXT,
                language    TEXT,
                duration_s  INTEGER,
                created_at  TEXT DEFAULT (datetime('now')),
                published_at TEXT,
                thumbnail   TEXT
            );

            CREATE TABLE IF NOT EXISTS performance (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id    INTEGER REFERENCES videos(id),
                recorded_at TEXT DEFAULT (datetime('now')),
                views       INTEGER DEFAULT 0,
                watch_mins  INTEGER DEFAULT 0,
                likes       INTEGER DEFAULT 0,
                comments    INTEGER DEFAULT 0,
                subs_gained INTEGER DEFAULT 0,
                cpm         REAL DEFAULT 0,
                revenue     REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS api_costs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                service     TEXT NOT NULL,
                operation   TEXT,
                units       REAL DEFAULT 0,
                cost_usd    REAL DEFAULT 0,
                video_id    INTEGER REFERENCES videos(id),
                recorded_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS topic_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic       TEXT NOT NULL,
                type        TEXT DEFAULT 'Planned',
                scheduled   TEXT,
                status      TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                added_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
            CREATE INDEX IF NOT EXISTS idx_videos_created_at ON videos(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_topic_queue_status ON topic_queue(status);
            CREATE INDEX IF NOT EXISTS idx_api_costs_video ON api_costs(video_id);
        """)
        # Add retry_count column if upgrading from older schema
        try:
            conn.execute("SELECT retry_count FROM topic_queue LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE topic_queue ADD COLUMN retry_count INTEGER DEFAULT 0")
        conn.commit()
    print(f"DB ready: {DB_PATH}")


# ── Videos ────────────────────────────────────────────────────
def log_video_start(topic, niche, language):
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO videos (topic, niche, language, status) VALUES (?,?,?,?)",
            (topic, niche, language, 'generating')
        )
        vid_id = cur.lastrowid
        conn.commit()
        return vid_id


def log_video_complete(vid_id, title, youtube_id, duration_s):
    with _conn() as conn:
        conn.execute(
            "UPDATE videos SET title=?, youtube_id=?, status='published', "
            "duration_s=?, published_at=datetime('now') WHERE id=?",
            (title, youtube_id, duration_s, vid_id)
        )
        conn.commit()


def log_video_error(vid_id, error_msg):
    with _conn() as conn:
        conn.execute(
            "UPDATE videos SET status='error', title=? WHERE id=?",
            (f"ERROR: {error_msg[:200]}", vid_id)
        )
        conn.commit()


def get_video_history(limit=50):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM videos ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Performance ───────────────────────────────────────────────
def log_performance(video_id, views, watch_mins, likes=0,
                    comments=0, subs_gained=0, cpm=1.5):
    revenue = (views / 1000) * cpm
    with _conn() as conn:
        conn.execute(
            "INSERT INTO performance (video_id,views,watch_mins,likes,"
            "comments,subs_gained,cpm,revenue) VALUES (?,?,?,?,?,?,?,?)",
            (video_id, views, watch_mins, likes, comments, subs_gained, cpm, revenue)
        )
        conn.commit()
    return revenue


def get_channel_stats():
    with _conn() as conn:
        stats = conn.execute("""
            SELECT
                COUNT(DISTINCT v.id)              AS total_videos,
                COALESCE(SUM(p.views),0)          AS total_views,
                COALESCE(SUM(p.watch_mins)/60.0,0) AS total_watch_hours,
                COALESCE(SUM(p.subs_gained),0)    AS total_subs,
                COALESCE(SUM(p.revenue),0)        AS total_revenue,
                COALESCE(AVG(p.views),0)          AS avg_views
            FROM videos v
            LEFT JOIN performance p ON p.video_id = v.id
            WHERE v.status = 'published'
        """).fetchone()
        return dict(stats)


# ── API Costs ─────────────────────────────────────────────────
def log_cost(service, operation, units, cost_usd, video_id=None):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO api_costs (service,operation,units,cost_usd,video_id) "
            "VALUES (?,?,?,?,?)",
            (service, operation, units, cost_usd, video_id)
        )
        conn.commit()


def get_monthly_costs(year=None, month=None):
    now = datetime.now()
    y = year or now.year
    m = month or now.month
    with _conn() as conn:
        rows = conn.execute("""
            SELECT service, SUM(cost_usd) AS total_cost, SUM(units) AS total_units,
                   COUNT(*) AS calls
            FROM api_costs
            WHERE strftime('%Y-%m', recorded_at) = ?
            GROUP BY service
            ORDER BY total_cost DESC
        """, (f"{y:04d}-{m:02d}",)).fetchall()
        return [dict(r) for r in rows]


def get_total_spent():
    with _conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) AS total FROM api_costs"
        ).fetchone()
        return row['total']


# ── YPP progress ──────────────────────────────────────────────
def get_ypp_progress():
    stats = get_channel_stats()
    subs = stats['total_subs']
    hours = stats['total_watch_hours']
    return {
        'subs': subs, 'subs_target': 1000,
        'subs_pct': min(100, round(subs/10)),
        'watch_hours': round(hours, 1),
        'watch_target': 4000,
        'watch_pct': min(100, round(hours/40)),
        'eligible': subs >= 1000 and hours >= 4000
    }


# ── Dashboard settings (SQLite replaces localStorage) ─────────────────────────
def get_settings() -> dict:
    """Return all settings rows as a dict with values JSON-parsed where possible."""
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        result: dict = {}
        for r in rows:
            try:
                result[r['key']] = json.loads(r['value'])
            except Exception:
                result[r['key']] = r['value']
        return result


def save_setting(key: str, value) -> None:
    """Upsert a single setting by key (value is JSON-serialised)."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (key, json.dumps(value, ensure_ascii=False))
        )
        conn.commit()