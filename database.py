"""
SQLite database layer for YouTube automation.
Tracks: video history, API costs, performance metrics.
Zero config — creates yt_automation.db automatically.
"""
import sqlite3
import json
from datetime import datetime

from config import DB_PATH

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = get_conn()
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
    conn.commit()
    conn.close()
    print(f"DB ready: {DB_PATH}")

# ── Videos ────────────────────────────────────────────────────
def log_video_start(topic, niche, language):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO videos (topic, niche, language, status) VALUES (?,?,?,?)",
        (topic, niche, language, 'generating')
    )
    vid_id = cur.lastrowid
    conn.commit(); conn.close()
    return vid_id

def log_video_complete(vid_id, title, youtube_id, duration_s):
    conn = get_conn()
    conn.execute(
        "UPDATE videos SET title=?, youtube_id=?, status='published', "
        "duration_s=?, published_at=datetime('now') WHERE id=?",
        (title, youtube_id, duration_s, vid_id)
    )
    conn.commit(); conn.close()

def log_video_error(vid_id, error_msg):
    conn = get_conn()
    conn.execute(
        "UPDATE videos SET status='error', title=? WHERE id=?",
        (f"ERROR: {error_msg[:200]}", vid_id)
    )
    conn.commit(); conn.close()

def get_video_history(limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM videos ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Performance ───────────────────────────────────────────────
def log_performance(video_id, views, watch_mins, likes=0,
                    comments=0, subs_gained=0, cpm=1.5):
    revenue = (views / 1000) * cpm
    conn = get_conn()
    conn.execute(
        "INSERT INTO performance (video_id,views,watch_mins,likes,"
        "comments,subs_gained,cpm,revenue) VALUES (?,?,?,?,?,?,?,?)",
        (video_id, views, watch_mins, likes, comments, subs_gained, cpm, revenue)
    )
    conn.commit(); conn.close()
    return revenue

def get_channel_stats():
    conn = get_conn()
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
    conn.close()
    return dict(stats)

# ── API Costs ─────────────────────────────────────────────────
def log_cost(service, operation, units, cost_usd, video_id=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO api_costs (service,operation,units,cost_usd,video_id) "
        "VALUES (?,?,?,?,?)",
        (service, operation, units, cost_usd, video_id)
    )
    conn.commit(); conn.close()

def get_monthly_costs(year=None, month=None):
    now = datetime.now()
    y = year or now.year
    m = month or now.month
    conn = get_conn()
    rows = conn.execute("""
        SELECT service, SUM(cost_usd) AS total_cost, SUM(units) AS total_units,
               COUNT(*) AS calls
        FROM api_costs
        WHERE strftime('%Y-%m', recorded_at) = ?
        GROUP BY service
        ORDER BY total_cost DESC
    """, (f"{y:04d}-{m:02d}",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_total_spent():
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd),0) AS total FROM api_costs"
    ).fetchone()
    conn.close()
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

# ── Initialise on explicit call only ─────────────────────────────────────────
# Call init_db() once at application startup (main.py, scheduler.py).
# Do NOT call it here — module imports should be side-effect-free.

# ── Dashboard settings (SQLite replaces localStorage) ─────────────────────────
def get_settings() -> dict:
    """Return all settings rows as a dict with values JSON-parsed where possible."""
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    result: dict = {}
    for r in rows:
        try:
            result[r['key']] = json.loads(r['value'])
        except Exception:
            result[r['key']] = r['value']
    return result


def save_setting(key: str, value) -> None:
    """Upsert a single setting by key (value is JSON-serialised)."""
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (key, json.dumps(value, ensure_ascii=False))
    )
    conn.commit()
    conn.close()