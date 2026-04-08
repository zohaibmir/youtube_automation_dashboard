"""scheduler.py — Automated publishing scheduler.

Single responsibility: run the pipeline on a configured weekly schedule
and keep the topic queue topped up. Nothing else.

Supports multi-channel uploads via --channel flag or SCHEDULER_CHANNEL env var.
"""

import logging
import time

import schedule

from config import (
    SCHEDULER_CHANNEL,
    SCHEDULER_PUBLISH_TIME,
    SCHEDULER_PUBLISH_TIMES,
    SCHEDULER_SHORTS_COUNT,
    VIDEOS_PER_WEEK,
)
from content_generator import generate_topic_ideas
from pipeline import run
from topic_queue import (
    dequeue_topic,
    enqueue_topics,
    mark_topic_done,
    mark_topic_failed,
    pending_count,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_DEFAULT_PUBLISH_TIME = "14:00"
_REFILL_THRESHOLD = 5
_CHANNEL_SLUG: str | None = None  # set by CLI --channel or env var


def _scheduler_shorts_count() -> int:
    """Return clamped scheduler shorts count (0-3)."""
    try:
        return max(0, min(3, int(SCHEDULER_SHORTS_COUNT)))
    except Exception:
        return 2


def _resolve_publish_time() -> str:
    """Return validated scheduler time in HH:MM 24h format."""
    raw = (SCHEDULER_PUBLISH_TIME or _DEFAULT_PUBLISH_TIME).strip()
    parts = raw.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        logger.warning("Invalid SCHEDULER_PUBLISH_TIME=%s; falling back to %s", raw, _DEFAULT_PUBLISH_TIME)
        return _DEFAULT_PUBLISH_TIME
    hour, minute = int(parts[0]), int(parts[1])
    if hour not in range(24) or minute not in range(60):
        logger.warning("Invalid SCHEDULER_PUBLISH_TIME=%s; falling back to %s", raw, _DEFAULT_PUBLISH_TIME)
        return _DEFAULT_PUBLISH_TIME
    return f"{hour:02d}:{minute:02d}"


def _resolve_publish_times() -> list[str]:
    """Return validated scheduler times in HH:MM 24h format."""
    raw_times = (SCHEDULER_PUBLISH_TIMES or "").strip()
    if not raw_times:
        return [_resolve_publish_time()]

    times: list[str] = []
    seen: set[str] = set()
    for raw in raw_times.split(","):
        candidate = raw.strip()
        if not candidate:
            continue
        parts = candidate.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            logger.warning("Skipping invalid scheduler time entry: %s", candidate)
            continue
        hour, minute = int(parts[0]), int(parts[1])
        if hour not in range(24) or minute not in range(60):
            logger.warning("Skipping invalid scheduler time entry: %s", candidate)
            continue
        normalized = f"{hour:02d}:{minute:02d}"
        if normalized not in seen:
            times.append(normalized)
            seen.add(normalized)

    if not times:
        fallback = _resolve_publish_time()
        logger.warning("No valid SCHEDULER_PUBLISH_TIMES found; falling back to %s", fallback)
        return [fallback]
    return sorted(times)


def refill_queue() -> None:
    """Generate and enqueue new topics when the queue runs low."""
    if pending_count() >= _REFILL_THRESHOLD:
        return
    logger.info("Queue low — generating new topics...")
    try:
        topics = generate_topic_ideas(count=10)
        if not topics:
            logger.warning("Queue refill returned no topics")
            return
        added = enqueue_topics(topics)
        logger.info("Added %d topics to the queue", added)
    except Exception as exc:
        logger.error("Queue refill failed: %s", exc)


def publish_next() -> None:
    """Process the next topic from the queue."""
    refill_queue()
    topic = dequeue_topic()
    if not topic:
        logger.warning("Queue empty — skipping this scheduled run")
        return
    shorts_count = _scheduler_shorts_count()
    logger.info(
        "Starting pipeline: %s (channel=%s, shorts=%d)",
        topic,
        _CHANNEL_SLUG or "default",
        shorts_count,
    )
    try:
        run(topic, channel_slug=_CHANNEL_SLUG, shorts_count=shorts_count)
        mark_topic_done(topic)
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        mark_topic_failed(topic)


def _setup_schedule() -> None:
    """Register publishing jobs based on VIDEOS_PER_WEEK."""
    publish_times = _resolve_publish_times()
    if len(publish_times) > 1:
        for publish_time in publish_times:
            schedule.every().day.at(publish_time).do(publish_next)
        logger.info("Schedule: daily at %s server time", ", ".join(publish_times))
        return

    publish_time = publish_times[0]
    if VIDEOS_PER_WEEK >= 7:
        schedule.every().day.at(publish_time).do(publish_next)
        logger.info("Schedule: daily at %s server time", publish_time)
    elif VIDEOS_PER_WEEK >= 5:
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
            getattr(schedule.every(), day).at(publish_time).do(publish_next)
        logger.info("Schedule: weekdays at %s server time", publish_time)
    else:
        for day in ["monday", "wednesday", "friday"]:
            getattr(schedule.every(), day).at(publish_time).do(publish_next)
        logger.info("Schedule: Mon/Wed/Fri at %s server time", publish_time)


def main() -> None:
    global _CHANNEL_SLUG
    import argparse
    parser = argparse.ArgumentParser(description="Automated YouTube publishing scheduler.")
    parser.add_argument("--channel", type=str, default=None,
                        help="YouTube channel slug from tokens/channels.json (e.g. 'default', 'main-channel')")
    args = parser.parse_args()
    _CHANNEL_SLUG = args.channel or SCHEDULER_CHANNEL or None

    from database import init_db
    init_db()
    logger.info("Scheduler starting — %d videos/week, channel=%s", VIDEOS_PER_WEEK, _CHANNEL_SLUG or "default")
    _setup_schedule()
    refill_queue()
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()