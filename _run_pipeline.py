"""One-shot pipeline runner — called by nohup, logs to /tmp/armageddon_pipeline.log

Usage:
    python _run_pipeline.py                         # use default channel
    python _run_pipeline.py --channel main-channel  # upload to specific channel
"""
import argparse
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("/tmp/armageddon_pipeline.log"),
        logging.StreamHandler(),
    ],
)

from database import init_db
init_db()

from pipeline import run

TOPIC = "Armageddon: What Islam, Christianity & Judaism All Say About the Final War and Return of Jesus"

parser = argparse.ArgumentParser(description="Run the video pipeline for a topic.")
parser.add_argument("--channel", type=str, default=None,
                    help="YouTube channel slug from tokens/channels.json (e.g. 'default', 'main-channel')")
args = parser.parse_args()

logging.info("=== Starting pipeline: %s (channel=%s) ===", TOPIC, args.channel or "default")
youtube_id = run(TOPIC, channel_slug=args.channel)
logging.info("=== DONE — https://youtube.com/watch?v=%s ===", youtube_id)
print(f"\n✅ DONE — https://youtube.com/watch?v={youtube_id}")
