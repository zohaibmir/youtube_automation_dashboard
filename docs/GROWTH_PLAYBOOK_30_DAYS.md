# YouTube Growth Playbook (30 Days)

This playbook is built for a new channel with limited daily time.

## Objective

- Publish consistently for 30 days.
- Deliver one long video and two Shorts every day.
- Use external distribution to generate first traffic while YouTube learns the channel.

## Daily Publishing Target

- Long video: 6 to 10 minutes.
- Shorts: 2 clips per long video.
- Posting cadence:
  - Long video: 1 per day.
  - Shorts: 2 per day.

## Core Strategy (High Impact, Low Time)

1. Keep topic focus narrow for 30 days (Gulf + South Asia geopolitics).
2. Use one visual style for thumbnails so viewers recognize your videos.
3. Front-load retention with a strong first 10 to 15 seconds.
4. Repurpose each long video into two Shorts and distribute everywhere.
5. Batch production weekly so daily work is mostly review and posting.

## 30-Day Execution System

1. Seed queue from the provided calendar file.
2. Run one topic daily with two Shorts.
3. Distribute each published asset to external platforms.
4. Track simple weekly metrics and optimize title/thumbnail/hook.

## Commands

### 1. Seed 30-day queue

```bash
source .venv/bin/activate
python3 scripts/seed_30_day_content.py --start-date 2026-04-06
```

### 2. Run one daily topic with 2 Shorts

```bash
source .venv/bin/activate
python3 scripts/run_pipeline.py --minutes 8 --language english --shorts 2 "<topic from queue>"
```

### 3. Optional: preview seed plan only

```bash
source .venv/bin/activate
python3 scripts/seed_30_day_content.py --start-date 2026-04-06 --dry-run
```

## Daily Distribution Checklist

After each upload, post to:

1. Instagram Reels (native caption and 3 to 5 hashtags)
2. Facebook Reels (same clip, different first line)
3. TikTok (short hook in first sentence)
4. Reddit (value-first post in relevant subreddits)
5. X or Threads (teaser + CTA to full video)

## Weekly Review (20 Minutes)

Track these metrics:

1. Long video CTR (target 4 to 8 percent)
2. Average view duration (target 35 to 50 percent)
3. Shorts viewed vs swiped away
4. Returning viewers
5. External traffic share

Then optimize:

1. Replace weak thumbnails for bottom 3 videos.
2. Rewrite first 15 seconds for next week scripts.
3. Keep topics close to top 3 performers.

## Fast Rules To Increase Views

1. One video should make one clear promise.
2. Use specific titles, not generic wording.
3. Keep Shorts tight (20 to 35 seconds unless retention stays high).
4. End each asset with one clear CTA.
5. Prioritize consistency over perfection for the first 30 days.
