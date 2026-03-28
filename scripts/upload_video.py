"""Upload a video + thumbnail + optional Shorts to YouTube.

Usage:
    python scripts/upload_video.py <video_path> [--channel <slug>] [--shorts <dir>]

Examples:
    python scripts/upload_video.py output/my-video.mp4
    python scripts/upload_video.py output/my-video.mp4 --channel truth-that-never-shared
    python scripts/upload_video.py output/my-video.mp4 --shorts output/shorts/
"""
import argparse
import glob
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

from youtube_uploader import upload_video, list_channels


def main():
    parser = argparse.ArgumentParser(description="Upload video to YouTube")
    parser.add_argument("video", help="Path to main video MP4")
    parser.add_argument("--thumb", default="thumbnail.jpg", help="Thumbnail image path")
    parser.add_argument("--title", required=True, help="Video title")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--channel", default=None, help="Channel slug (default channel if omitted)")
    parser.add_argument("--shorts", default=None, help="Directory containing Short MP4s to upload")
    args = parser.parse_args()

    if not os.path.isfile(args.video):
        print(f"Error: video not found: {args.video}")
        sys.exit(1)

    content = {
        "title": args.title,
        "description": args.description,
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
    }

    print(f"Uploading: {args.video}")
    vid_id = upload_video(args.video, args.thumb, content, channel_slug=args.channel)
    print(f"Published: https://youtube.com/watch?v={vid_id}")

    if args.shorts and os.path.isdir(args.shorts):
        shorts = sorted(glob.glob(os.path.join(args.shorts, "*.mp4")))
        for i, sp in enumerate(shorts, 1):
            short_content = {
                "title": f"{args.title} Part {i} #Shorts",
                "description": args.description,
                "tags": content["tags"] + ["Shorts"],
            }
            try:
                sid = upload_video(sp, args.thumb, short_content, channel_slug=args.channel)
                print(f"Short #{i}: https://youtube.com/watch?v={sid}")
            except Exception as e:
                print(f"Short #{i} failed: {e}")


if __name__ == "__main__":
    main()
