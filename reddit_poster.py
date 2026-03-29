"""reddit_poster.py — Post YouTube videos to Reddit after upload.

Posts a link submission to each configured subreddit. Failures are logged
and silently skipped so they never block the main pipeline.

Requirements:
  pip install praw

Credentials must be set in .env (NOT via the dashboard):
  REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD

Optional runtime config (can be set from dashboard):
  REDDIT_ENABLED, REDDIT_SUBREDDITS, REDDIT_POST_FLAIR
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def post_to_reddit(
    title: str,
    youtube_url: str,
    subreddits_csv: Optional[str] = None,
    flair: Optional[str] = None,
) -> list[str]:
    """Submit a YouTube link to one or more subreddits.

    Returns a list of Reddit post URLs for every successful submission.
    Never raises — all per-subreddit exceptions are caught and logged.
    """
    try:
        import praw  # ImportError is handled below
    except ImportError:
        logger.error("reddit_poster: 'praw' is not installed. Run: pip install praw")
        return []

    from config import (
        REDDIT_CLIENT_ID,
        REDDIT_CLIENT_SECRET,
        REDDIT_USERNAME,
        REDDIT_PASSWORD,
        REDDIT_SUBREDDITS,
        REDDIT_POST_FLAIR,
    )

    client_id = REDDIT_CLIENT_ID.strip()
    client_secret = REDDIT_CLIENT_SECRET.strip()
    username = REDDIT_USERNAME.strip()
    password = REDDIT_PASSWORD.strip()

    if not all([client_id, client_secret, username, password]):
        logger.warning(
            "reddit_poster: credentials missing — set REDDIT_CLIENT_ID, "
            "REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD in .env"
        )
        return []

    # Subreddits: prefer argument, fallback to config
    raw = subreddits_csv or REDDIT_SUBREDDITS or ""
    subreddits = [s.strip().lstrip("r/") for s in raw.split(",") if s.strip()]
    if not subreddits:
        logger.warning("reddit_poster: no subreddits configured — skipping")
        return []

    # Flair: prefer argument, fallback to config
    post_flair = flair if flair is not None else REDDIT_POST_FLAIR

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=f"youtube_automation:v1.0 (by u/{username})",
        )
        # Verify auth — will raise if credentials are wrong
        reddit.user.me()
    except Exception as exc:
        logger.error("reddit_poster: authentication failed — %s", exc)
        return []

    posted_urls: list[str] = []

    for sub_name in subreddits:
        try:
            subreddit = reddit.subreddit(sub_name)
            submission_kwargs: dict = {
                "title": title,
                "url": youtube_url,
                "resubmit": True,
                "send_replies": False,
            }

            # Apply flair if provided and the subreddit has it
            if post_flair:
                try:
                    flairs = list(subreddit.flair.link_templates.user_selectable())
                    match = next(
                        (f for f in flairs if post_flair.lower() in f["flair_text"].lower()),
                        None,
                    )
                    if match:
                        submission_kwargs["flair_id"] = match["flair_template_id"]
                except Exception:
                    pass  # Flair not critical — skip silently

            submission = subreddit.submit_link(**submission_kwargs)  # type: ignore[arg-type]
            url = f"https://reddit.com{submission.permalink}"
            posted_urls.append(url)
            logger.info("reddit_poster: posted to r/%s → %s", sub_name, url)

        except Exception as exc:
            logger.warning("reddit_poster: r/%s — %s", sub_name, exc)

    return posted_urls
