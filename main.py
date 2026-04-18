"""main.py — CLI entry point.

Single responsibility: parse the command-line argument and kick off
the pipeline. All logic lives in pipeline.py and its dependencies.

Usage:
    python main.py "your topic here"
    python main.py                      # uses default topic
"""

import logging
import argparse

from database import init_db
from pipeline import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Run YouTube pipeline for a topic")
    parser.add_argument("topic", nargs="*", help="Topic text")
    parser.add_argument("--channel", dest="channel_slug", default=None,
                        help="Channel slug from tokens/channels.json")
    parser.add_argument("--shorts", dest="shorts_count", type=int, default=None,
                        help="Number of companion shorts to generate (0-3)")
    args = parser.parse_args()

    topic = " ".join(args.topic).strip() or "10 paise bachane ki aadat"
    run(topic, channel_slug=args.channel_slug, shorts_count=args.shorts_count)