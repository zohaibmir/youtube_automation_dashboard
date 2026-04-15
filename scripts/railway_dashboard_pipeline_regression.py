#!/usr/bin/env python3
"""Regression test for dashboard pipeline context on Railway.

This script targets the deployed dashboard API and simulates the payload the
dashboard should send after earlier steps are completed.

It validates that per-run context survives from the dashboard into the
pipeline for two channels by sending:
  - channel_slug
  - language
  - scriptText
  - optional voice_id (resolved from channel voice endpoint)

Default channels match the current Railway deployment:
  - Newsstudio -> Hinglish
  - Truth that never shared -> English

Usage:
  python3 scripts/railway_dashboard_pipeline_regression.py
  python3 scripts/railway_dashboard_pipeline_regression.py --skip-upload
  python3 scripts/railway_dashboard_pipeline_regression.py --base-url https://your-app.up.railway.app
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib import error, request


DEFAULT_BASE_URL = os.getenv(
    "DASHBOARD_BASE_URL",
    "https://youtubeautomationdashboard-production.up.railway.app",
)
DEFAULT_POLL_SECONDS = 12
DEFAULT_MAX_WAIT_SECONDS = 60 * 90


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _resolve_auth(cli_user: str | None, cli_password: str | None) -> tuple[str, str]:
    env = _load_env_file(Path(".env"))
    user = cli_user or os.getenv("DASHBOARD_USERNAME") or env.get("DASHBOARD_USERNAME", "")
    password = cli_password or os.getenv("DASHBOARD_PASSWORD") or env.get("DASHBOARD_PASSWORD", "")
    if not user or not password:
        raise RuntimeError(
            "Missing dashboard credentials. Set DASHBOARD_USERNAME and DASHBOARD_PASSWORD, "
            "or pass --username and --password."
        )
    return user, password


def _auth_headers(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _call(base_url: str, headers: dict[str, str], path: str,
          method: str = "GET", body: dict | None = None,
          timeout: int = 120) -> tuple[int, dict]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(base_url.rstrip("/") + path, data=payload, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"ok": False, "error": raw or f"HTTP {exc.code}"}
        return exc.code, data


def _normalize_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _find_channel(channels: list[dict], expected_name: str) -> dict:
    target = _normalize_name(expected_name)
    for channel in channels:
        if _normalize_name(channel.get("name", "")) == target:
            return channel
    for channel in channels:
        if target in _normalize_name(channel.get("name", "")):
            return channel
    raise RuntimeError(f"Channel not found on server: {expected_name}")


def _fetch_channels(base_url: str, headers: dict[str, str]) -> list[dict]:
    status, data = _call(base_url, headers, "/api/channels")
    if status != 200 or not data.get("ok"):
        raise RuntimeError(f"Failed to fetch channels: {data}")
    return data.get("channels", [])


def _fetch_channel_voice(base_url: str, headers: dict[str, str], slug: str) -> str | None:
    status, data = _call(base_url, headers, f"/api/channels/{slug}/voice")
    if status != 200 or not data.get("ok"):
        return None
    return (data.get("voice_id") or "").strip() or None


def _wait_for_pipeline(base_url: str, headers: dict[str, str],
                       expected_topic: str, expected_channel_slug: str,
                       poll_seconds: int, max_wait_seconds: int) -> dict:
    started = time.time()
    last_message = ""
    while True:
        _, status = _call(base_url, headers, "/api/pipeline/status")
        state = status.get("status")
        topic = status.get("topic")
        channel_slug = status.get("channel_slug")
        message = status.get("message", "")
        if message:
            last_message = message

        if topic == expected_topic and state in ("ready", "failed"):
            return status

        if time.time() - started > max_wait_seconds:
            return {
                "status": "failed",
                "error": "timeout waiting for ready",
                "message": last_message,
                "topic": topic,
                "channel_slug": channel_slug,
            }

        print(
            f"  poll status={state} topic={topic} channel={channel_slug} "
            f"msg={message[:100]}"
        )
        time.sleep(poll_seconds)


def _english_script() -> str:
    return """[HOOK - 0:00]
Most creators are wasting half their week on repetitive work, and in 2026 that is the fastest way to fall behind. The real gap now is not talent. It is how intelligently you use AI tools to move faster without losing quality.

[SEGMENT 1 - THE REAL PROBLEM]
Small creators still edit thumbnails manually, rewrite titles three times, and spend hours turning rough ideas into publishable scripts. That old workflow kills consistency. If a creator needs eight hours just to prepare one video, the channel never compounds.

[SEGMENT 2 - TOOL ONE]
The first tool is AI research summarization. Instead of reading twenty tabs, creators can feed trusted sources into one workflow and pull out the strongest claims, facts, and talking points in minutes. This is where idea quality improves before recording even starts.

[SEGMENT 3 - TOOL TWO]
The second tool is script drafting with structure prompts. A good AI draft is not about replacing thinking. It is about starting with a strong hook, clear segment flow, and a better first version than a blank page ever gives you.

[SEGMENT 4 - TOOL THREE]
The third tool is smart title and thumbnail ideation. The best creators test multiple packaging angles before they publish. AI makes that iteration cheap. Instead of guessing one title, you generate ten and keep the strongest emotional angle.

[SEGMENT 5 - TOOL FOUR]
The fourth tool is voice and audio automation. Clean narration, leveling, and timing used to be a bottleneck. Now creators can maintain a consistent tone across videos while spending far less time on repetitive audio cleanup.

[SEGMENT 6 - TOOL FIVE]
The fifth tool is auto-clipping for short-form distribution. One long-form video can become multiple short assets, and that multiplies impressions without multiplying production effort.

[SEGMENT 7 - TOOL SIX]
The sixth tool is workflow automation across publishing. If the script, thumbnail, metadata, and upload flow are connected, the creator stops restarting from zero every time. That is where channels begin to feel like systems instead of random bursts of work.

[SEGMENT 8 - TOOL SEVEN]
The seventh tool is analytics interpretation. Raw numbers are not enough. Creators need actionable signals like where retention drops, which hook formats win, and what topics are worth doubling down on next week.

[OUTRO]
The creators winning in 2026 are not doing more busywork. They are building tighter systems. If you use AI to remove friction while keeping your judgment sharp, you create faster, publish more consistently, and improve with every upload."""


def _hinglish_script() -> str:
    return """[HOOK - 0:00]
Aaj sabse bada problem yeh nahi hai ke logon ke paas ideas nahi hain. Problem yeh hai ke achha idea pipeline mein enter hota hai aur end tak pahunchte pahunchte uska asli tone hi change ho jata hai. Agar aap Hinglish audience ke liye bana rahe ho aur final video English mein nikal aaye, to pura channel signal weak ho jata hai.

[SEGMENT 1 - WHY THIS MATTERS]
Audience ko sirf topic nahi chahiye hota. Unko apni language, apna rhythm, aur apna familiar tone chahiye hota hai. Hinglish content tab kaam karta hai jab explanation practical ho, examples relatable ho, aur sentences naturally Hindi aur English mix mein flow karein.

[SEGMENT 2 - STUDENT SIDE HUSTLE ONE]
Pehla practical side hustle hai short-form video editing for local businesses and creators. Bohat se creators ko captions, cuts, hooks, aur thumbnail packaging chahiye hoti hai, lekin unke paas time nahi hota. Student weekend par bhi kaafi projects handle kar sakta hai.

[SEGMENT 3 - SIDE HUSTLE TWO]
Doosra side hustle hai AI-assisted content repurposing. Ek long video ko newsletter, shorts, carousel, aur blog summary mein convert karna ab fast ho gaya hai. Client ko output chahiye hota hai, process se unko matlab nahi hota.

[SEGMENT 4 - SIDE HUSTLE THREE]
Teesra option hai niche research service. Bohat se founders aur creators ko trend research, competitor breakdown, aur content angle mapping chahiye hoti hai. Agar aap structured research de sakte ho, to bina camera ke kaam mil sakta hai.

[SEGMENT 5 - SIDE HUSTLE FOUR]
Chautha side hustle hai thumbnail concepting. Sirf design nahi, packaging sochna valuable skill hai. Kis emotion par click aayega, kis phrase se curiosity banegi, aur kis contrast se CTR improve hoga, yeh samajhna high-value skill hai.

[SEGMENT 6 - SIDE HUSTLE FIVE]
Paanchwa option hai community management aur reply workflows. Bohat se growing channels comments, DMs, aur follow-up interactions manage nahi kar paate. Student yeh operations handle karke monthly retainer model create kar sakta hai.

[SEGMENT 7 - WHAT TO AVOID]
Lekin ek galti mat karna. Sirf random freelancing gigs chase mat karo. Ek clear skill choose karo, uska simple portfolio banao, phir usko ek repeatable offer mein package karo. Isi se stable income banti hai.

[OUTRO]
2026 mein side hustle jeetne ka formula simple hai: low-cost skill, fast delivery, clear outcome. Agar aap Hinglish audience ko target kar rahe ho, to communication bhi waise hi rakho jaisa unko naturally samajh aaye. Tabhi trust banta hai aur tabhi content convert karta hai."""


def _build_cases() -> list[dict]:
    return [
        {
            "channel_name": "Newsstudio",
            "topic": "Railway dashboard regression: Newsstudio Hinglish payload upload",
            "language": "hinglish",
            "script_text": _hinglish_script(),
            "seo_title": "Best Side Hustles in 2026 for Students",
            "seo_description": "Hinglish breakdown of practical student side hustles in 2026. Focused on real skills, faster execution, and repeatable income.",
            "seo_tags": [
                "side hustle 2026",
                "students income",
                "hinglish business",
                "freelancing for students",
                "online income guide",
            ],
        },
        {
            "channel_name": "Truth that never shared",
            "topic": "Railway dashboard regression: Truth channel English payload upload",
            "language": "english",
            "script_text": _english_script(),
            "seo_title": "Top 7 AI Tools That Save Creators Hours in 2026",
            "seo_description": "English creator workflow breakdown covering AI tools for research, scripting, packaging, automation, and analytics.",
            "seo_tags": [
                "ai tools 2026",
                "creator workflow",
                "youtube productivity",
                "automation for creators",
                "content systems",
            ],
        },
    ]


def _run_case(base_url: str, headers: dict[str, str], case: dict,
              channels: list[dict], skip_upload: bool,
              poll_seconds: int, max_wait_seconds: int) -> dict:
    channel = _find_channel(channels, case["channel_name"])
    slug = channel.get("slug", "")
    if not slug:
        return {"ok": False, "stage": "resolve", "error": f"Missing slug for {case['channel_name']}"}

    voice_id = _fetch_channel_voice(base_url, headers, slug)

    print(f"\n=== START [{case['channel_name']}] slug={slug} lang={case['language']} voice={voice_id or 'channel/global default'} ===")

    _call(base_url, headers, "/api/pipeline/cancel", "POST", {})

    payload = {
        "topic": case["topic"],
        "channel_slug": slug,
        "language": case["language"],
        "scriptText": case["script_text"],
        "seoTitle": case["seo_title"],
        "seoDescription": case["seo_description"],
        "seoTags": ", ".join(case["seo_tags"]),
        "shortsCount": 0,
    }
    if voice_id:
        payload["voice_id"] = voice_id

    code, run_resp = _call(base_url, headers, "/api/pipeline/run", "POST", payload, timeout=180)
    if code != 200 or not run_resp.get("ok"):
        return {"ok": False, "stage": "run", "error": str(run_resp), "channel_slug": slug}

    status = _wait_for_pipeline(
        base_url, headers,
        expected_topic=case["topic"],
        expected_channel_slug=slug,
        poll_seconds=poll_seconds,
        max_wait_seconds=max_wait_seconds,
    )

    if status.get("channel_slug") != slug:
        return {
            "ok": False,
            "stage": "status",
            "error": f"Pipeline status channel mismatch: expected {slug}, got {status.get('channel_slug')}",
            "channel_slug": slug,
            "status": status,
        }

    if status.get("status") != "ready":
        return {
            "ok": False,
            "stage": "generate",
            "error": status.get("error") or status.get("message") or "unknown",
            "channel_slug": slug,
            "status": status,
        }

    if skip_upload:
        return {
            "ok": True,
            "stage": "ready",
            "channel_slug": slug,
            "title": status.get("title"),
            "voice_id": voice_id,
        }

    up_code, up_resp = _call(
        base_url,
        headers,
        "/api/pipeline/upload",
        "POST",
        {"channel": slug},
        timeout=3600,
    )
    if up_code != 200 or not up_resp.get("ok"):
        return {
            "ok": False,
            "stage": "upload",
            "error": str(up_resp),
            "channel_slug": slug,
            "voice_id": voice_id,
        }

    return {
        "ok": True,
        "stage": "done",
        "channel_slug": slug,
        "title": up_resp.get("title") or status.get("title"),
        "youtube_url": up_resp.get("youtube_url"),
        "youtube_id": up_resp.get("youtube_id"),
        "voice_id": voice_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Railway dashboard pipeline regression for two channels")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Dashboard base URL")
    parser.add_argument("--username", default=None, help="Dashboard basic-auth username")
    parser.add_argument("--password", default=None, help="Dashboard basic-auth password")
    parser.add_argument("--skip-upload", action="store_true", help="Generate to ready state only")
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS, help="Pipeline poll interval")
    parser.add_argument("--timeout-minutes", type=int, default=DEFAULT_MAX_WAIT_SECONDS // 60, help="Max minutes to wait per run")
    args = parser.parse_args()

    username, password = _resolve_auth(args.username, args.password)
    headers = _auth_headers(username, password)
    channels = _fetch_channels(args.base_url, headers)

    print(f"Using base URL: {args.base_url}")
    print(f"Discovered channels: {', '.join(ch.get('name', '?') for ch in channels)}")

    cases = _build_cases()
    max_wait_seconds = max(args.timeout_minutes, 1) * 60
    all_ok = True
    results: list[dict] = []

    for case in cases:
        result = _run_case(
            args.base_url,
            headers,
            case,
            channels,
            args.skip_upload,
            args.poll_seconds,
            max_wait_seconds,
        )
        result["channel_name"] = case["channel_name"]
        result["language"] = case["language"]
        results.append(result)

        if result.get("ok"):
            print(
                f"PASS [{case['channel_name']}] stage={result.get('stage')} "
                f"slug={result.get('channel_slug')} url={result.get('youtube_url')}"
            )
        else:
            print(
                f"FAIL [{case['channel_name']}] stage={result.get('stage')} "
                f"slug={result.get('channel_slug')} error={result.get('error')}"
            )
            all_ok = False

    print("\n=== SUMMARY ===")
    for result in results:
        print(json.dumps(result, ensure_ascii=False))

    return 0 if all_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())