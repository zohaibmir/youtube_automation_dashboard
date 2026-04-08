"""topic_queue.py — Database-backed topic queue management.

Single responsibility: manage the lifecycle of topics in the
topic_queue table (enqueue, dequeue, mark done/failed).
Nothing else.

Replaces the previous JSON file approach in scheduler.py.
"""

import logging

from database import _conn

logger = logging.getLogger(__name__)

_REFILL_THRESHOLD = 5
_MAX_RETRIES = 3


def enqueue_topics(topics: list[str], topic_type: str = "AI-generated") -> int:
    """Insert topics into the queue with status='pending'.

    Returns the number of rows inserted.
    """
    with _conn() as conn:
        base_priority = conn.execute(
            "SELECT COALESCE(MAX(priority), 0) FROM topic_queue WHERE status='pending'"
        ).fetchone()[0]
        rows = []
        for idx, t in enumerate(topics, start=1):
            rows.append((t, topic_type, int(base_priority) + idx))
        conn.executemany(
            "INSERT INTO topic_queue (topic, type, status, priority) VALUES (?, ?, 'pending', ?)",
            rows,
        )
        conn.commit()
        added = conn.total_changes
    logger.info("Enqueued %d topics", added)
    return added


def dequeue_topic() -> str | None:
    """Pop and return the next pending topic (max retries not exceeded).

    Uses BEGIN EXCLUSIVE to prevent two concurrent callers from
    selecting the same row.
    Returns None if the queue is empty.
    """
    with _conn() as conn:
        conn.execute("BEGIN EXCLUSIVE")
        try:
            row = conn.execute(
                "SELECT id, topic FROM topic_queue "
                "WHERE status='pending' AND retry_count < ? "
                "ORDER BY priority ASC, id ASC LIMIT 1",
                (_MAX_RETRIES,),
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            conn.execute(
                "UPDATE topic_queue SET status='processing' WHERE id=?", (row["id"],)
            )
            conn.commit()
            logger.info("Dequeued topic: %s", row["topic"])
            return row["topic"]
        except Exception:
            conn.rollback()
            raise


def mark_topic_done(topic: str) -> None:
    """Mark the most recent 'processing' instance of a topic as 'done'."""
    with _conn() as conn:
        conn.execute(
            "UPDATE topic_queue SET status='done' WHERE topic=? AND status='processing'",
            (topic,),
        )
        conn.commit()


def mark_topic_failed(topic: str) -> None:
    """Re-queue a failed topic with incremented retry count.

    Topics that exceed _MAX_RETRIES attempts stay as 'failed' permanently.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, retry_count FROM topic_queue "
            "WHERE topic=? AND status='processing' ORDER BY id DESC LIMIT 1",
            (topic,),
        ).fetchone()
        if not row:
            return
        new_count = (row["retry_count"] or 0) + 1
        if new_count >= _MAX_RETRIES:
            conn.execute(
                "UPDATE topic_queue SET status='failed', retry_count=? WHERE id=?",
                (new_count, row["id"]),
            )
            logger.error("Topic permanently failed after %d attempts: %s", new_count, topic)
        else:
            conn.execute(
                "UPDATE topic_queue SET status='pending', retry_count=? WHERE id=?",
                (new_count, row["id"]),
            )
            logger.warning("Topic re-queued (attempt %d/%d): %s", new_count, _MAX_RETRIES, topic)
        conn.commit()


def pending_count() -> int:
    """Return the number of topics waiting to be processed."""
    with _conn() as conn:
        count: int = conn.execute(
            "SELECT COUNT(*) FROM topic_queue WHERE status='pending' AND retry_count < ?",
            (_MAX_RETRIES,),
        ).fetchone()[0]
        return count


def get_pending_topics(limit: int = 200) -> list[dict]:
    """Return pending topics in dequeue order (top item runs next)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, topic, type, status, priority, added_at "
            "FROM topic_queue "
            "WHERE status='pending' AND retry_count < ? "
            "ORDER BY priority ASC, id ASC LIMIT ?",
            (_MAX_RETRIES, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def reorder_pending_topics(ordered_ids: list[int]) -> int:
    """Persist a new priority order for pending queue items.

    Args:
        ordered_ids: Full ordered list of pending queue row IDs.

    Returns:
        Number of rows updated.
    """
    clean_ids = [int(i) for i in ordered_ids if str(i).isdigit()]
    if not clean_ids:
        return 0

    with _conn() as conn:
        conn.execute("BEGIN EXCLUSIVE")
        try:
            rows = conn.execute(
                "SELECT id FROM topic_queue "
                "WHERE status='pending' AND retry_count < ? "
                "ORDER BY priority ASC, id ASC",
                (_MAX_RETRIES,),
            ).fetchall()
            existing = [int(r["id"]) for r in rows]
            existing_set = set(existing)

            # Keep caller order for known IDs, then append any omitted IDs.
            ordered = [i for i in clean_ids if i in existing_set]
            ordered_set = set(ordered)
            ordered.extend([i for i in existing if i not in ordered_set])

            changed = 0
            for priority, item_id in enumerate(ordered, start=1):
                conn.execute(
                    "UPDATE topic_queue SET priority=? WHERE id=?",
                    (priority, item_id),
                )
                changed += 1
            conn.commit()
            return changed
        except Exception:
            conn.rollback()
            raise
