"""One-off test: generate an 8+ min video on a trending personal finance topic."""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ["PYTHONUNBUFFERED"] = "1"

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    stream=sys.stderr)

from database import init_db
from pipeline import run

TOPIC = "Why 90 Percent Indians Will Never Be Rich - 7 Money Traps That Keep Middle Class Poor"

GUIDANCE = """IMPORTANT: Generate at least 16 segments (minimum 16, up to 20).
Each segment narration should be 40-50 seconds when spoken aloud.
Total video must be 8-10 minutes long.
Make it dramatic, use real statistics and Indian examples.
Cover these 7 traps: EMI trap, lifestyle inflation, no emergency fund, gold obsession, FD over equity, insurance scams (endowment plans), real estate myth.
End with actionable steps to escape the middle-class trap.
Use hinglish naturally — mix Hindi phrases into English narration."""

if __name__ == "__main__":
    init_db()
    vid_id = run(TOPIC, guidance=GUIDANCE, shorts_count=2)
    print(f"\nDONE — YouTube ID: {vid_id}", file=sys.stderr)
    sys.stderr.flush()
