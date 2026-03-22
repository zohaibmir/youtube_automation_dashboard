"""scheduler.py — Automated publishing scheduler.

Single responsibility: run the pipeline on a configured weekly schedule
and keep the topic queue topped up. Nothing else.
"""

import logging
import time

import schedule

from config import VIDEOS_PER_WEEK
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

_PUBLISH_TIME = "14:00"       # 14:00 UTC = 7:30 PM IST / 7 PM PKT
_REFILL_THRESHOLD = 5


def refill_queue() -> None:
    """Generate and enqueue new topics when the queue runs low."""
    if pending_count() >= _REFILL_THRESHOLD:
        return
    logger.info("Queue low — generating new topics...")
    topics = generate_topic_ideas(count=10)
    added = enqueue_topics(topics)
    logger.info("Added %d topics to the queue", added)


def publish_next() -> None:
    """Process the next topic from the queue."""
    refill_queue()
    topic = dequeue_topic()
    if not topic:
        logger.warning("Queue empty — skipping this scheduled run")
        return
    logger.info("Starting pipeline: %s", topic)
    try:
        run(topic)
        mark_topic_done(topic)
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        mark_topic_failed(topic)


def _setup_schedule() -> None:
    """Register publishing jobs based on VIDEOS_PER_WEEK."""
    if VIDEOS_PER_WEEK >= 7:
        schedule.every().day.at(_PUBLISH_TIME).do(publish_next)
        logger.info("Schedule: daily at %s UTC", _PUBLISH_TIME)
    elif VIDEOS_PER_WEEK >= 5:
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
            getattr(schedule.every(), day).at(_PUBLISH_TIME).do(publish_next)
        logger.info("Schedule: weekdays at %s UTC", _PUBLISH_TIME)
    else:
        for day in ["monday", "wednesday", "friday"]:
            getattr(schedule.every(), day).at(_PUBLISH_TIME).do(publish_next)
        logger.info("Schedule: Mon/Wed/Fri at %s UTC", _PUBLISH_TIME)


def main() -> None:
    from database import init_db
    init_db()
    logger.info("Scheduler starting — %d videos/week", VIDEOS_PER_WEEK)
    _setup_schedule()
    refill_queue()
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()