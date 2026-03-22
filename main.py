"""main.py — CLI entry point.

Single responsibility: parse the command-line argument and kick off
the pipeline. All logic lives in pipeline.py and its dependencies.

Usage:
    python main.py "your topic here"
    python main.py                      # uses default topic
"""

import logging
import sys

from database import init_db
from pipeline import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if __name__ == "__main__":
    init_db()
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "10 paise bachane ki aadat"
    run(topic)