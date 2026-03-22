"""content_generator.py — AI-powered script and topic generation.

Single responsibility: interact with the Claude API to produce
video scripts and topic ideas. Nothing else.
"""

import json
import logging

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CHANNEL_AUDIENCE,
    CHANNEL_LANGUAGE,
    CHANNEL_NICHE,
    CLAUDE_MODEL,
)

logger = logging.getLogger(__name__)


def generate_script(topic: str) -> dict:
    """Generate a full video script for the given topic.

    Returns a dict with keys: title, description, tags,
    thumbnail_text, thumbnail_subtext, segments.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Niche: {CHANNEL_NICHE} | Audience: {CHANNEL_AUDIENCE} | Language: {CHANNEL_LANGUAGE}
Topic: "{topic}"

Return ONLY valid JSON:
{{
  "title": "under 65 chars",
  "description": "3 paragraphs + 6 hashtags",
  "tags": ["tag1", "...15 tags total"],
  "thumbnail_text": "5-7 word ALL CAPS",
  "thumbnail_subtext": "3-4 words",
  "segments": [
    {{
      "type": "hook",
      "narration": "30sec shocking opener",
      "visual_keyword": "2-word search",
      "caption": "short caption"
    }}
  ]
}}

Min 10 segments. Hook = shocking fact or question.
Use {CHANNEL_LANGUAGE} naturally. Short sentences. Build suspense."""

    logger.info("Generating script for topic: %s", topic)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text
    script = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    logger.info("Script generated: %d segments", len(script.get("segments", [])))
    return script


def script_text_to_segments(script_text: str, topic: str, seo_override: dict | None = None) -> dict:
    """Convert a human-written dashboard script into the pipeline's segment format.

    Used when the user writes/edits script in the Script Writer tab before
    running the pipeline — avoids regenerating the script from scratch.

    Args:
        script_text:   Raw script text from the dashboard's Script Writer.
        topic:         The video topic (used for fallback title).
        seo_override:  Dict with 'title', 'description', 'tags' from SEO tab.
                       If provided, those values override Claude's suggestions.

    Returns:
        Same dict shape as generate_script(): title, description, tags,
        thumbnail_text, thumbnail_subtext, segments.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Convert this YouTube script into pipeline segments.
Niche: {CHANNEL_NICHE} | Audience: {CHANNEL_AUDIENCE} | Language: {CHANNEL_LANGUAGE}
Topic: "{topic}"

Script:
{script_text[:3500]}

Return ONLY valid JSON — do not regenerate the script, keep the exact narration text from above:
{{
  "title": "SEO-optimized title under 65 chars",
  "description": "2-3 paragraphs + 6 hashtags",
  "tags": ["tag1", "...15 tags total"],
  "thumbnail_text": "5-7 word ALL CAPS emotional hook",
  "thumbnail_subtext": "3-4 words",
  "segments": [
    {{
      "type": "hook|segment|outro",
      "narration": "exact verbatim text from script for this section",
      "visual_keyword": "2-word pexels video search term",
      "caption": "6-8 word on-screen caption"
    }}
  ]
}}
Split into 8-12 segments of roughly equal length."""

    logger.info("Converting dashboard script to segments for topic: %s", topic)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",  # cheap — just formatting, not writing
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text
    result = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])

    # Apply SEO overrides if provided
    if seo_override:
        if seo_override.get("title"):
            result["title"] = seo_override["title"]
        if seo_override.get("description"):
            result["description"] = seo_override["description"]
        if seo_override.get("tags"):
            result["tags"] = seo_override["tags"]

    logger.info("Script converted: %d segments", len(result.get("segments", [])))
    return result


def generate_topic_ideas(count: int = 10) -> list[str]:
    """Generate trending topic ideas for the channel.

    Returns a list of topic strings.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Generate {count} trending YouTube topics for a {CHANNEL_NICHE} channel.
Audience: {CHANNEL_AUDIENCE}. Language: {CHANNEL_LANGUAGE}.
Return ONLY a JSON array of strings. Mix Hinglish and English.
Make them clickable and searchable."""

    logger.info("Generating %d topic ideas", count)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text
    ideas = json.loads(raw[raw.index("[") : raw.rindex("]") + 1])
    logger.info("Generated %d topic ideas", len(ideas))
    return ideas
