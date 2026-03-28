"""Run the full pipeline for one topic via CLI.

Usage:
    python scripts/run_pipeline.py "Your Topic Here"
    python scripts/run_pipeline.py "Your Topic" --channel truth-that-never-shared --shorts
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Run full video pipeline for a topic")
    parser.add_argument("topic", help="Video topic / title")
    parser.add_argument("--channel", default=None, help="YouTube channel slug")
    parser.add_argument("--shorts", action="store_true", help="Also build Shorts")
    parser.add_argument("--upload", action="store_true", help="Upload to YouTube after build")
    parser.add_argument("--social", action="store_true", help="Upload to social platforms too")
    args = parser.parse_args()

    from pipeline import run

    result = run(
        topic=args.topic,
        channel_slug=args.channel,
        shorts_count=2 if args.shorts else 0,
    )

    if result:
        print(f"\nPipeline complete.")
        if isinstance(result, dict):
            for k, v in result.items():
                print(f"  {k}: {v}")
    else:
        print("Pipeline failed — check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
