"""Seed a 30-day content plan into topic_queue.

Reads data/content_plan_30_days.csv and inserts long-video topics as pending
queue items with a scheduled date. Shorts are generated at runtime by running
scripts/run_pipeline.py with --shorts 2 for each topic.

Usage:
    python3 scripts/seed_30_day_content.py --start-date 2026-04-06
    python3 scripts/seed_30_day_content.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import _conn, init_db


REPO_ROOT = Path(__file__).resolve().parents[1]
CALENDAR_FILE = REPO_ROOT / "data" / "content_plan_30_days.csv"


def _parse_start_date(start_date: str | None) -> date:
    if not start_date:
        return date.today()
    return datetime.strptime(start_date, "%Y-%m-%d").date()


def _load_rows() -> list[dict[str, str]]:
    if not CALENDAR_FILE.exists():
        raise FileNotFoundError(f"Calendar not found: {CALENDAR_FILE}")

    with CALENDAR_FILE.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader]

    if not rows:
        raise ValueError("Calendar file is empty")
    return rows


def seed_plan(start_date: date, dry_run: bool, force: bool) -> tuple[int, int]:
    rows = _load_rows()
    inserted = 0
    skipped = 0

    with _conn() as conn:
        for row in rows:
            day_number = int(row["day"])
            topic = (row.get("long_video_topic") or "").strip()
            scheduled_date = (start_date + timedelta(days=day_number - 1)).isoformat()

            if not topic:
                skipped += 1
                continue

            if not force:
                exists = conn.execute(
                    "SELECT 1 FROM topic_queue WHERE topic = ? LIMIT 1",
                    (topic,),
                ).fetchone()
                if exists:
                    skipped += 1
                    continue

            if dry_run:
                print(f"[DRY RUN] day={day_number:02d} date={scheduled_date} topic={topic}")
                inserted += 1
                continue

            conn.execute(
                """
                INSERT INTO topic_queue (topic, type, scheduled, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (topic, "30-day-plan", scheduled_date),
            )
            inserted += 1

        if not dry_run:
            conn.commit()

    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed 30-day content plan into topic_queue")
    parser.add_argument(
        "--start-date",
        default=None,
        help="Start date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview queue inserts without writing to database",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Insert topics even if matching topic text already exists",
    )
    args = parser.parse_args()

    init_db()
    start_date = _parse_start_date(args.start_date)
    inserted, skipped = seed_plan(start_date=start_date, dry_run=args.dry_run, force=args.force)

    print(f"Start date: {start_date.isoformat()}")
    print(f"Calendar: {CALENDAR_FILE}")
    print(f"Inserted: {inserted}")
    print(f"Skipped: {skipped}")

    if args.dry_run:
        print("Dry run complete. No DB changes were made.")
    else:
        print("Queue seed complete.")
        print("Run daily: python3 scripts/run_pipeline.py --minutes 8 --language english --shorts 2 \"<topic>\"")


if __name__ == "__main__":
    main()
