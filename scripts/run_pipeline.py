"""Run the full pipeline for one topic via CLI.

Usage:
    python scripts/run_pipeline.py "Your Topic Here"
    python scripts/run_pipeline.py --language english --minutes 8 --shorts 2 "Your Topic"
    python scripts/run_pipeline.py --channel truth-that-never-shared --upload --social "Your Topic"
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


def build_guidance(language: str | None, minutes: int | None) -> str | None:
    pieces: list[str] = []

    if language:
        pieces.append(f"Write the script in {language}.")
    pieces.append("Use clear, factual documentary narration suitable for YouTube.")
    pieces.append("Keep the tone serious, readable, and high-retention.")

    if minutes:
        approx_segments = max(8, min(22, int(minutes * 2)))
        pieces.append(f"Target runtime: about {minutes} minutes.")
        pieces.append(
            f"Create about {approx_segments} narration segments so the final video lands near that runtime."
        )
        pieces.append("Keep each segment around 25 to 40 seconds of spoken narration.")
    else:
        pieces.append("Target runtime: medium-length YouTube documentary.")

    pieces.append("Include a strong hook, clear progression, and a decisive closing.")
    return " ".join(pieces)


def main():
    parser = argparse.ArgumentParser(description="Run full video pipeline for a topic")
    parser.add_argument("topic", help="Video topic / title")
    parser.add_argument("--channel", default=None, help="YouTube channel slug")
    parser.add_argument("--language", default=None, help="Script language/style, e.g. english, urdu, hindi")
    parser.add_argument("--minutes", type=int, default=None, help="Approximate target runtime in minutes")
    parser.add_argument("--shorts", type=int, default=0, help="How many Shorts to generate (0-3)")
    parser.add_argument("--upload", action="store_true", help="Kept for backward compatibility; pipeline uploads by default")
    parser.add_argument("--social", action="store_true", help="Kept for backward compatibility")
    args = parser.parse_args()

    from database import init_db
    from pipeline import run

    init_db()
    shorts_count = max(0, min(3, args.shorts))
    guidance = build_guidance(args.language, args.minutes)

    result = run(
        topic=args.topic,
        channel_slug=args.channel,
        guidance=guidance,
        shorts_count=shorts_count,
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
