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


def enqueue_topics(topics: list[str], topic_type: str = "AI-generated", channel_slug: str | None = None) -> int:
    """Insert topics into the queue with status='pending'.

    Returns the number of rows inserted.
    """
    with _conn() as conn:
        if channel_slug:
            base_priority = conn.execute(
                "SELECT COALESCE(MAX(priority), 0) FROM topic_queue WHERE status='pending' AND channel_slug=?",
                (channel_slug,),
            ).fetchone()[0]
        else:
            base_priority = conn.execute(
                "SELECT COALESCE(MAX(priority), 0) FROM topic_queue WHERE status='pending' AND channel_slug IS NULL"
            ).fetchone()[0]
        rows = []
        for idx, t in enumerate(topics, start=1):
            rows.append((t, channel_slug, topic_type, int(base_priority) + idx))
        conn.executemany(
            "INSERT INTO topic_queue (topic, channel_slug, type, status, priority) VALUES (?, ?, ?, 'pending', ?)",
            rows,
        )
        conn.commit()
        added = conn.total_changes
    logger.info("Enqueued %d topics", added)
    return added


def dequeue_topic_item(channel_slug: str | None = None) -> dict | None:
    """Pop and return the next pending topic (max retries not exceeded).

    Uses BEGIN EXCLUSIVE to prevent two concurrent callers from
    selecting the same row.
    Returns None if the queue is empty.
    """
    with _conn() as conn:
        conn.execute("BEGIN EXCLUSIVE")
        try:
            if channel_slug:
                row = conn.execute(
                    "SELECT id, topic, channel_slug FROM topic_queue "
                    "WHERE status='pending' AND retry_count < ? AND channel_slug=? "
                    "ORDER BY priority ASC, id ASC LIMIT 1",
                    (_MAX_RETRIES, channel_slug),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id, topic, channel_slug FROM topic_queue "
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
            item = {"id": row["id"], "topic": row["topic"], "channel_slug": row["channel_slug"]}
            logger.info("Dequeued topic: %s (id=%s channel=%s)", item["topic"], item["id"], item["channel_slug"])
            return item
        except Exception:
            conn.rollback()
            raise


def dequeue_topic(channel_slug: str | None = None) -> str | None:
    """Backward-compatible wrapper that returns only topic text."""
    item = dequeue_topic_item(channel_slug=channel_slug)
    return item["topic"] if item else None


def mark_topic_done(topic: str | None = None, channel_slug: str | None = None, topic_id: int | None = None) -> None:
    """Mark the most recent 'processing' instance of a topic as 'done'."""
    with _conn() as conn:
        if topic_id is not None:
            conn.execute(
                "UPDATE topic_queue SET status='done' WHERE id=? AND status='processing'",
                (int(topic_id),),
            )
        elif topic:
            if channel_slug:
                conn.execute(
                    "UPDATE topic_queue SET status='done' WHERE topic=? AND channel_slug=? AND status='processing'",
                    (topic, channel_slug),
                )
            else:
                conn.execute(
                    "UPDATE topic_queue SET status='done' WHERE topic=? AND status='processing'",
                    (topic,),
                )
        conn.commit()


def mark_topic_failed(topic: str | None = None, channel_slug: str | None = None, topic_id: int | None = None) -> None:
    """Re-queue a failed topic with incremented retry count.

    Topics that exceed _MAX_RETRIES attempts stay as 'failed' permanently.
    """
    with _conn() as conn:
        if topic_id is not None:
            row = conn.execute(
                "SELECT id, topic, retry_count FROM topic_queue "
                "WHERE id=? AND status='processing' ORDER BY id DESC LIMIT 1",
                (int(topic_id),),
            ).fetchone()
        elif topic and channel_slug:
            row = conn.execute(
                "SELECT id, topic, retry_count FROM topic_queue "
                "WHERE topic=? AND channel_slug=? AND status='processing' ORDER BY id DESC LIMIT 1",
                (topic, channel_slug),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, topic, retry_count FROM topic_queue "
                "WHERE topic=? AND status='processing' ORDER BY id DESC LIMIT 1",
                (topic,),
            ).fetchone()
        if not row:
            return
        new_count = (row["retry_count"] or 0) + 1
        topic_text = row["topic"]
        if new_count >= _MAX_RETRIES:
            conn.execute(
                "UPDATE topic_queue SET status='failed', retry_count=? WHERE id=?",
                (new_count, row["id"]),
            )
            logger.error("Topic permanently failed after %d attempts: %s", new_count, topic_text)
        else:
            conn.execute(
                "UPDATE topic_queue SET status='pending', retry_count=? WHERE id=?",
                (new_count, row["id"]),
            )
            logger.warning("Topic re-queued (attempt %d/%d): %s", new_count, _MAX_RETRIES, topic_text)
        conn.commit()


def pending_count(channel_slug: str | None = None) -> int:
    """Return the number of topics waiting to be processed."""
    with _conn() as conn:
        if channel_slug:
            count: int = conn.execute(
                "SELECT COUNT(*) FROM topic_queue WHERE status='pending' AND retry_count < ? AND channel_slug=?",
                (_MAX_RETRIES, channel_slug),
            ).fetchone()[0]
        else:
            count = conn.execute(
                "SELECT COUNT(*) FROM topic_queue WHERE status='pending' AND retry_count < ?",
                (_MAX_RETRIES,),
            ).fetchone()[0]
        return count


def get_pending_topics(limit: int = 200, channel_slug: str | None = None) -> list[dict]:
    """Return pending topics in dequeue order (top item runs next)."""
    with _conn() as conn:
        if channel_slug:
            rows = conn.execute(
                "SELECT id, topic, channel_slug, type, status, priority, added_at "
                "FROM topic_queue "
                "WHERE status='pending' AND retry_count < ? AND channel_slug=? "
                "ORDER BY priority ASC, id ASC LIMIT ?",
                (_MAX_RETRIES, channel_slug, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, topic, channel_slug, type, status, priority, added_at "
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


def delete_topic(topic_id: int) -> bool:
    """Delete a topic from the queue by ID.

    Returns True if a row was deleted, False otherwise.
    """
    try:
        with _conn() as conn:
            conn.execute("DELETE FROM topic_queue WHERE id=?", (int(topic_id),))
            conn.commit()
            deleted = conn.total_changes > 0
            if deleted:
                logger.info("Deleted queue topic ID %d", topic_id)
            return deleted
    except Exception as e:
        logger.error("Failed to delete queue topic ID %d: %s", topic_id, e)
        return False
