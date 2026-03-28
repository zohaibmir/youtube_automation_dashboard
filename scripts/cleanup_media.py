"""Clean up generated media files from output directories.

Usage:
    python scripts/cleanup_media.py              # dry-run (show what would be deleted)
    python scripts/cleanup_media.py --confirm     # actually delete
    python scripts/cleanup_media.py --older 7     # only files older than 7 days
"""
import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_DIRS = ["output", "shorts_output", "temp", "media_cache"]
EXTENSIONS = {".mp4", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".webp"}


def find_media(older_days=None):
    cutoff = time.time() - (older_days * 86400) if older_days else None
    files = []
    for d in MEDIA_DIRS:
        dirpath = os.path.join(ROOT, d)
        if not os.path.isdir(dirpath):
            continue
        for root, _, filenames in os.walk(dirpath):
            for f in filenames:
                if os.path.splitext(f)[1].lower() in EXTENSIONS:
                    fp = os.path.join(root, f)
                    if cutoff and os.path.getmtime(fp) > cutoff:
                        continue
                    files.append(fp)
    return files


def fmt_size(b):
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"


def main():
    parser = argparse.ArgumentParser(description="Clean generated media files")
    parser.add_argument("--confirm", action="store_true", help="Actually delete (default is dry-run)")
    parser.add_argument("--older", type=int, default=None, help="Only delete files older than N days")
    args = parser.parse_args()

    files = find_media(args.older)
    if not files:
        print("No media files found to clean.")
        return

    total = sum(os.path.getsize(f) for f in files)
    print(f"Found {len(files)} media files ({fmt_size(total)}):")
    for f in files[:20]:
        print(f"  {os.path.relpath(f, ROOT)}  ({fmt_size(os.path.getsize(f))})")
    if len(files) > 20:
        print(f"  ... and {len(files) - 20} more")

    if not args.confirm:
        print("\nDry run — pass --confirm to delete.")
        return

    deleted = 0
    for f in files:
        try:
            os.remove(f)
            deleted += 1
        except OSError as e:
            print(f"  Failed: {f}: {e}")

    print(f"\nDeleted {deleted}/{len(files)} files, freed {fmt_size(total)}")


if __name__ == "__main__":
    main()
