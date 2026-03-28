"""community_post.py — Generate YouTube community post drafts using AI.

YouTube Data API has no community post creation endpoint, so this module
generates ready-to-copy post text that the user can paste into YouTube Studio.
Supports Anthropic Claude for content generation.
"""

import json
import os

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def generate_post(title: str, description: str, tags: list[str] | None = None,
                  api_key: str | None = None) -> dict:
    """Generate a community post draft based on video metadata.

    Args:
        title: Video title.
        description: Video description.
        tags: Optional list of tags for context.
        api_key: Anthropic API key (falls back to ANTHROPIC_API_KEY env var).

    Returns:
        {"ok": True, "post": str, "hashtags": str}
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return _fallback_post(title, description, tags)

    try:
        import urllib.request
        tag_str = ", ".join(tags[:15]) if tags else ""
        prompt = f"""You are a YouTube community post writer. Write an engaging community post
to promote this video. The post should:
- Be 150-300 characters (short and punchy)
- Start with an attention-grabbing hook or emoji
- Include a call-to-action (watch, comment, share)
- End with 3-5 relevant hashtags on a new line
- Match the tone/topic of the video
- Do NOT include the video link (YouTube adds it automatically)

Video Title: {title}
Description: {description[:500]}
Tags: {tag_str}

Return ONLY the post text, nothing else."""

        body = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            _ANTHROPIC_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        post_text = "\n".join(text_blocks).strip()
        if not post_text:
            return _fallback_post(title, description, tags)

        return {"ok": True, "post": post_text, "source": "ai"}

    except Exception as e:
        # Fall back to template if AI fails
        result = _fallback_post(title, description, tags)
        result["ai_error"] = str(e)
        return result


def _fallback_post(title: str, description: str,
                   tags: list[str] | None = None) -> dict:
    """Generate a simple template-based post when AI is unavailable."""
    hook = description[:120].rstrip(".") + "…" if len(description) > 120 else description
    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in (tags or [])[:5])
    post = f"🔥 NEW VIDEO: {title}\n\n{hook}\n\n👉 Watch now and let me know what you think!\n\n{hashtags}"
    return {"ok": True, "post": post, "source": "template"}
