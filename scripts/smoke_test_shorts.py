"""smoke_test_shorts.py - lightweight smoke checks for animated shorts feature.

No external API calls are made. This test monkey-patches clip generation to keep
it fast and deterministic.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

errors: list[tuple[str, Exception]] = []


def check(label: str, fn) -> None:
    try:
        fn()
        print(f"  OK  {label}")
    except Exception as exc:
        errors.append((label, exc))
        print(f"  FAIL {label}: {exc}")


def test_imports() -> None:
    __import__("animated_visual_fetcher")
    __import__("shorts_pipeline")
    __import__("server")


def test_shorts_pipeline_dry_run() -> None:
    import animated_visual_fetcher as avf
    import shorts_pipeline as sp

    out_dir = Path("output/smoke_shorts")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Preserve and patch generator to avoid remote API calls
    original = avf.generate_animated_short

    def fake_generate_animated_short(topic: str, hooks: list[str], out_dir: str, aspect_ratio: str = "9:16") -> list[str]:
        paths = []
        for i, _ in enumerate(hooks[:2]):
            p = Path(out_dir) / f"fake_{i:03d}.mp4"
            p.write_bytes(b"fake-mp4")
            paths.append(str(p))
        return paths

    avf.generate_animated_short = fake_generate_animated_short
    try:
        out = sp.run_animated_shorts_pipeline(
            topic="Smoke Test Topic",
            hooks=["Scene one", "Scene two"],
            out_dir=str(out_dir),
            aspect_ratio="9:16",
            platforms=[],
        )
        assert isinstance(out, dict)
        assert "paths" in out
        assert len(out["paths"]) == 2
        for p in out["paths"]:
            assert p.startswith("/")
            assert Path(p.lstrip("/")).exists()
    finally:
        avf.generate_animated_short = original


def test_server_routes_present() -> None:
    with open("server.py", "r", encoding="utf-8") as f:
        text = f.read()
    assert "/api/shorts/generate-animated" in text
    assert "/api/shorts/status" in text
    assert "/api/shorts/list" in text
    assert "/api/shorts/distribute" in text
    assert "/api/shorts/pipeline/run" in text


if __name__ == "__main__":
    print("Python:", sys.version.split()[0])
    print()

    check("imports (animated_visual_fetcher, shorts_pipeline, server)", test_imports)
    check("shorts_pipeline dry run", test_shorts_pipeline_dry_run)
    check("server shorts routes present", test_server_routes_present)

    print()
    if errors:
        print(f"FAILED - {len(errors)} error(s)")
        for label, exc in errors:
            print(f"  - {label}: {exc}")
        raise SystemExit(1)
    print("ALL SHORTS SMOKE CHECKS PASSED")
