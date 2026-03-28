"""Manage YouTube channels: list, add, remove, set default.

Usage:
    python scripts/manage_channels.py list
    python scripts/manage_channels.py add
    python scripts/manage_channels.py default <slug>
    python scripts/manage_channels.py remove <slug>
"""
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Manage YouTube channels")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all configured channels")
    sub.add_parser("add", help="Add a new channel via OAuth")
    rm = sub.add_parser("remove", help="Remove a channel")
    rm.add_argument("slug", help="Channel slug to remove")
    df = sub.add_parser("default", help="Set the default channel")
    df.add_argument("slug", help="Channel slug to set as default")

    args = parser.parse_args()

    from youtube_uploader import list_channels, add_channel, remove_channel, set_default_channel

    if args.cmd == "list":
        channels = list_channels()
        if not channels:
            print("No channels configured.")
            return
        for ch in channels:
            star = " ⭐" if ch.get("default") else ""
            print(f"  {ch['slug']}: {ch.get('channel_id', 'N/A')}{star}")

    elif args.cmd == "add":
        slug = add_channel()
        print(f"Added channel: {slug}")

    elif args.cmd == "remove":
        remove_channel(args.slug)
        print(f"Removed: {args.slug}")

    elif args.cmd == "default":
        set_default_channel(args.slug)
        print(f"Default set to: {args.slug}")


if __name__ == "__main__":
    main()
