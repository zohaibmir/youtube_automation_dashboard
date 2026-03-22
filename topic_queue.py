"""topic_queue.py — Database-backed topic queue management.

Single responsibility: manage the lifecycle of topics in the
topic_queue table (enqueue, dequeue, mark done/failed).
Nothing else.

Replaces the previous JSON file approach in scheduler.py.
"""

import logging

from database import get_conn

logger = logging.getLogger(__name__)

_REFILL_THRESHOLD = 5


def enqueue_topics(topics: list[str], topic_type: str = "AI-generated") -> int:
    """Insert topics into the queue with status='pending'.

    Returns the number of rows inserted.
    """
    conn = get_conn()
    conn.executemany(
        "INSERT INTO topic_queue (topic, type, status) VALUES (?, ?, 'pending')",
        [(t, topic_type) for t in topics],
    )
    conn.commit()
    added = conn.total_changes
    conn.close()
    logger.info("Enqueued %d topics", added)
    return added


def dequeue_topic() -> str | None:
    """Pop and return the next pending topic.

    Atomically marks it as 'processing' so it is not picked up twice.
    Returns None if the queue is empty.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT id, topic FROM topic_queue WHERE status='pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute(
        "UPDATE topic_queue SET status='processing' WHERE id=?", (row["id"],)
    )
    conn.commit()
    conn.close()
    logger.info("Dequeued topic: %s", row["topic"])
    return row["topic"]


def mark_topic_done(topic: str) -> None:
    """Mark the most recent 'processing' instance of a topic as 'done'."""
    conn = get_conn()
    conn.execute(
        "UPDATE topic_queue SET status='done' WHERE topic=? AND status='processing'",
        (topic,),
    )
    conn.commit()
    conn.close()


def mark_topic_failed(topic: str) -> None:
    """Re-queue a failed topic so it will be retried on the next run."""
    conn = get_conn()
    conn.execute(
        "UPDATE topic_queue SET status='pending' WHERE topic=? AND status='processing'",
        (topic,),
    )
    conn.commit()
    conn.close()
    logger.warning("Topic re-queued for retry: %s", topic)


def pending_count() -> int:
    """Return the number of topics waiting to be processed."""
    conn = get_conn()
    count: int = conn.execute(
        "SELECT COUNT(*) FROM topic_queue WHERE status='pending'"
    ).fetchone()[0]
    conn.close()
    return count
