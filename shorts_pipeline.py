"""shorts_pipeline.py - dedicated animated Shorts orchestration.

This module keeps Shorts-only generation/distribution separate from the
long-form pipeline flow in pipeline.py.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable


def run_animated_shorts_pipeline(
    topic: str,
    hooks: list[str],
    out_dir: str,
    aspect_ratio: str = "9:16",
    platforms: list[str] | None = None,
    title: str | None = None,
    description: str = "",
    tags: list[str] | None = None,
    progress_cb: Callable[[str, int], None] | None = None,
) -> dict:
    """Generate animated short clips and optionally distribute them.

    Returns:
      {
        "paths": ["output/shorts_animated/<job>/clip.mp4", ...],
        "results": [...],
      }
    """
    from animated_visual_fetcher import generate_animated_short

    if progress_cb:
        progress_cb("generating", 10)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    local_paths = generate_animated_short(
        topic=topic,
        hooks=hooks,
        out_dir=out_dir,
        aspect_ratio=aspect_ratio,
    )
    if not local_paths:
        raise RuntimeError("No clips were generated")

    if progress_cb:
        progress_cb("generated", 65)

    # Convert local paths to server-style relative paths
    rel_paths = ["/" + p.lstrip("/") for p in local_paths]

    dist_results: list[dict] = []
    if platforms:
        if progress_cb:
            progress_cb("distributing", 80)
        dist_results = distribute_shorts(
            clip_paths=rel_paths,
            platforms=platforms,
            title=title or topic[:100] or "AI Animated Short",
            description=description,
            tags=tags or [],
        )

    if progress_cb:
        progress_cb("done", 100)

    return {
        "paths": rel_paths,
        "results": dist_results,
    }


def distribute_shorts(
    clip_paths: list[str],
    platforms: list[str],
    title: str,
    description: str,
    tags: list[str],
) -> list[dict]:
    """Upload shorts clips to selected platforms using existing upload modules."""
    results: list[dict] = []

    for rel_path in clip_paths:
        local_path = rel_path.lstrip("/")
        if not os.path.isfile(local_path):
            results.append({"path": rel_path, "error": "File not found"})
            continue

        clip_result = {"path": rel_path, "uploaded": {}, "errors": {}}
        content = {
            "title": title[:100],
            "description": description,
            "tags": tags,
        }

        if "youtube" in platforms:
            try:
                from youtube_uploader import upload_video as _yt_upload

                yt_id = _yt_upload(local_path, None, content)
                clip_result["uploaded"]["youtube"] = f"https://youtube.com/shorts/{yt_id}"
            except Exception as ex:
                clip_result["errors"]["youtube"] = str(ex)

        social_platforms = [p for p in platforms if p in ("instagram", "facebook", "tiktok")]
        if social_platforms:
            try:
                from social_uploader import upload_to_platforms

                social_result = upload_to_platforms(
                    local_path,
                    title=title,
                    description=description,
                    caption=title,
                    platforms_list=social_platforms,
                )
                for plat, res in social_result.items():
                    if res.get("ok"):
                        clip_result["uploaded"][plat] = res.get("id", "ok")
                    else:
                        clip_result["errors"][plat] = res.get("error", "unknown")
            except Exception as ex:
                for platform in social_platforms:
                    clip_result["errors"][platform] = str(ex)

        results.append(clip_result)

    return results
