"""smoke_test.py — Verify all module imports and core DB functionality."""
import sys

errors = []

print(f"Python: {sys.version.split()[0]}")
print()

def check(label, fn):
    try:
        fn()
        print(f"  ✓  {label}")
    except Exception as exc:
        errors.append((label, exc))
        print(f"  ✗  {label}: {exc}")

# ── Imports ───────────────────────────────────────────────────
check("config", lambda: __import__("config"))
check("voice_config", lambda: __import__("voice_config"))

def test_database():
    from database import init_db, get_conn, get_channel_stats
    init_db()
    stats = get_channel_stats()
    assert "total_videos" in stats
check("database (init_db + get_channel_stats)", test_database)

check("content_generator", lambda: __import__("content_generator"))
check("audio_generator",   lambda: __import__("audio_generator"))
check("visual_fetcher",    lambda: __import__("visual_fetcher"))
check("video_builder",     lambda: __import__("video_builder"))
check("thumbnail",         lambda: __import__("thumbnail"))
check("youtube_uploader",  lambda: __import__("youtube_uploader"))

def test_topic_queue():
    from database import init_db
    init_db()
    import topic_queue
    count = topic_queue.pending_count()
    assert isinstance(count, int)
check("topic_queue (pending_count)", test_topic_queue)

check("pipeline",     lambda: __import__("pipeline"))
check("hybrid_mode",  lambda: __import__("hybrid_mode"))
check("scheduler",    lambda: __import__("scheduler"))

# ── Syntax check main.py ──────────────────────────────────────
def test_main_syntax():
    import ast
    with open("main.py") as f:
        ast.parse(f.read())
check("main.py syntax", test_main_syntax)

# ── Summary ───────────────────────────────────────────────────
print()
if errors:
    print(f"FAILED — {len(errors)} error(s):")
    for label, exc in errors:
        print(f"  • {label}: {exc}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED ✓")
