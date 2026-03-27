"""content_generator.py — AI-powered script and topic generation.

Single responsibility: interact with the Claude API to produce
video scripts and topic ideas. Nothing else.
"""

import json
import logging
import re
import time

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CHANNEL_AUDIENCE,
    CHANNEL_LANGUAGE,
    CHANNEL_NICHE,
    CLAUDE_MODEL,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3

# ── Per-model pricing (per 1M tokens) — update when Anthropic changes rates ──
_MODEL_PRICING = {
    "claude-sonnet-4-20250514":  {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}
_DEFAULT_PRICING = {"input": 3.00, "output": 15.00}


def _calc_cost(model: str, usage) -> float:
    """Calculate USD cost from an Anthropic message Usage object."""
    pricing = _MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return (
        usage.input_tokens * pricing["input"] / 1_000_000
        + usage.output_tokens * pricing["output"] / 1_000_000
    )


def _call_claude(model: str, max_tokens: int, messages: list) -> anthropic.types.Message:
    """Call Claude with exponential backoff (3 attempts)."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError,
                anthropic.InternalServerError) as e:
            if attempt == _MAX_RETRIES:
                raise
            wait = 2 ** attempt
            logger.warning("Claude retry %d/%d: %s (wait %ds)", attempt, _MAX_RETRIES, e, wait)
            time.sleep(wait)


def _extract_json(raw: str) -> dict:
    """Robustly extract a JSON object from Claude's response text.

    Handles: bare JSON, ```json fenced blocks, and markdown-wrapped output.
    """
    # Try markdown code block first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Fall back to outermost { … } with proper brace matching
    start = raw.index("{")
    depth = 0
    for i, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : i + 1])
    # Last resort: naive slice
    return json.loads(raw[raw.index("{") : raw.rindex("}") + 1])


def generate_script(topic: str, guidance: str | None = None) -> dict:
    """Generate a full video script for the given topic.

    Args:
        topic:    The video topic string.
        guidance: Optional creator instructions to guide the AI's script style/content.

    Returns a dict with keys: title, description, tags,
    thumbnail_text, thumbnail_subtext, segments.
    """
    guidance_block = ""
    if guidance:
        guidance_block = f"""

--- CREATOR INSTRUCTIONS (follow these carefully) ---
{guidance}
---
"""

    prompt = f"""Niche: {CHANNEL_NICHE} | Audience: {CHANNEL_AUDIENCE} | Language: {CHANNEL_LANGUAGE}
Topic: "{topic}"
{guidance_block}
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
      "visual_keyword": "3-5 word specific visual description for Pexels stock search",
      "visual_keyword_fallback": "2-word simpler fallback search",
      "caption": "short caption"
    }}
  ]
}}

Min 10 segments. Hook = shocking fact or question.
Use {CHANNEL_LANGUAGE} naturally. Short sentences. Build suspense.
For visual_keyword: be specific and descriptive — e.g. 'ancient temple ruins sunset', 'crowded mosque prayer', 'jerusalem old city wall'. Avoid single generic words.
For visual_keyword_fallback: use a simpler 1-2 word broad term in case the specific one has no results."""

    logger.info("Generating script for topic: %s", topic)
    msg = _call_claude(CLAUDE_MODEL, 3000, [{"role": "user", "content": prompt}])
    raw = msg.content[0].text
    script = _extract_json(raw)
    script["_usage"] = {
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
        "cost_usd": _calc_cost(CLAUDE_MODEL, msg.usage),
    }
    logger.info("Script generated: %d segments (cost $%.4f)", len(script.get("segments", [])), script["_usage"]["cost_usd"])
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
      "visual_keyword": "3-5 word specific visual description for Pexels",
      "visual_keyword_fallback": "2-word simpler fallback term",
      "caption": "6-8 word on-screen caption"
    }}
  ]
}}
Split into 8-12 segments of roughly equal length.
For visual_keyword: be specific — e.g. 'mosque interior golden dome', 'soldier battlefield smoke', 'bible open light rays'. Avoid single generic words.
For visual_keyword_fallback: 1-2 word broad fallback if specific term has no results."""

    logger.info("Converting dashboard script to segments for topic: %s", topic)
    _convert_model = "claude-haiku-4-5-20251001"
    msg = _call_claude(_convert_model, 3000, [{"role": "user", "content": prompt}])
    raw = msg.content[0].text
    result = _extract_json(raw)
    result["_usage"] = {
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
        "cost_usd": _calc_cost(_convert_model, msg.usage),
    }

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
    prompt = f"""Generate {count} trending YouTube topics for a {CHANNEL_NICHE} channel.
Audience: {CHANNEL_AUDIENCE}. Language: {CHANNEL_LANGUAGE}.
Return ONLY a JSON array of strings. Mix Hinglish and English.
Make them clickable and searchable."""

    logger.info("Generating %d topic ideas", count)
    msg = _call_claude(CLAUDE_MODEL, 1000, [{"role": "user", "content": prompt}])
    raw = msg.content[0].text
    ideas = json.loads(raw[raw.index("[") : raw.rindex("]") + 1])
    logger.info("Generated %d topic ideas", len(ideas))
    return ideas
