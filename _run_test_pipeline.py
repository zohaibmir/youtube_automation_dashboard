"""
Production video: 7 Ancient Prophecies Being Fulfilled RIGHT NOW in 2026.

TARGET AUDIENCE : India, Pakistan, Gulf diaspora, global English speakers
CHANNEL         : Truth that never shared (default)
EXPECTED LENGTH : 10-12 minutes
SHORTS          : 2 (hook clip + prophecy #1)

WHY THIS TOPIC WINS:
  - Multi-religion appeal (Islamic Hadith, Biblical, Hindu Vedic) = maximum reach
  - "RIGHT NOW 2026" urgency = high search volume + click-through
  - India angle = 1.4B audience + Gulf expats (Indian + Pakistani)
  - Covers Gaza, Trump, AI, India rise — all trending in March 2026
  - English = global CPM ($3-8 US/UK/AU) + India ($1.5-3)
  - "Truth/Hidden" framing = high retention conspiracy-curious viewers
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ["PYTHONUNBUFFERED"] = "1"

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    stream=sys.stderr)

from database import init_db
from pipeline import run

TOPIC = "7 Ancient Prophecies Being FULFILLED Right Now in 2026 — Signs The World Is Changing Forever"

GUIDANCE = """
You are writing a high-retention YouTube documentary script for a global English-speaking audience
that includes India, Pakistan, Gulf diaspora, and Western viewers interested in politics and religion.

VIDEO STRUCTURE (minimum 18 segments, target 20):
Each segment narration = 35-45 seconds spoken at a calm documentary pace.
Total runtime: 10-12 minutes.

TONE: Authoritative, dramatic, documentary. Like a National Geographic narrator crossed with
a geopolitics analyst. No sensationalism — present FACTS and let them create the shock.

HOOK (segment 1, ~45 sec):
Start with a shocking statement: "Right now, in 2026, three ancient prophecies from three
different religions — written over 1400 years apart — are being fulfilled simultaneously.
What you're about to see is not a coincidence." Then preview all 7 prophecies by name.

THE 7 PROPHECIES (2 segments each — setup + modern fulfillment):

1. THE BAREFOOT PROPHECY (Islamic Hadith — Sahih Muslim)
   Prophecy: "The Hour will not come until barefoot, destitute shepherds compete in building
   tall buildings." Modern fulfillment: UAE/Saudi skylines. Dubai's Burj Khalifa. Riyadh's NEOM.
   Qatar's World Cup stadiums. Show the contrast — Bedouins to billionaires in 60 years.
   INDIA CONNECTION: India's own billionaire skyline boom — Mumbai's Antilia next to slums.

2. THE GREAT FIRE IN HEJAZ (Islamic Hadith — Bukhari/Muslim)
   Prophecy: A great fire will emerge from the Hijaz region (Arabian Peninsula) illuminating
   camel necks in Syria. Modern: Saudi Arabia's gas flares visible from space. The region
   literally burning with conflict — Gaza, Yemen, Syria. Use satellite imagery description.

3. THE RIVERS OF BLOOD IN THE HOLY LAND (Biblical — Revelation 6, Isaiah 34)
   Prophecy: "The land will be soaked with blood... the sword of the Lord is filled with blood."
   Modern: Gaza 2023-2026. 45,000+ killed. UN calling it one of history's fastest civilian
   casualty rates. The Euphrates drying up (Turkey dams). INDIA CONNECTION: India abstained
   from key UN votes — its geopolitical positioning in the Gaza crisis.

4. THE DRYING OF THE EUPHRATES (Islamic Hadith + Biblical Revelation 16:12)
   Prophecy: The Euphrates river will dry up, revealing treasures beneath it. Modern:
   The Euphrates is at historic lows — Turkey's Ataturk Dam, drought, climate change.
   Iraq farmers abandoning fields. SHOCKING STAT: River flow reduced 40% since 1977.

5. THE RISE OF THE EAST — INDIA AND CHINA (Hindu Vedic Prophecy + modern geopolitics)
   Prophecy: From Bhavishya Purana and modern interpretations — the era of Kali Yuga's end
   sees Eastern civilizations reclaiming power. Modern: India is now the world's 5th largest
   economy, projected #2 by 2075. China's Belt and Road. The shift of global power from West
   to East. INDIA ANGLE: Modi's "Viksit Bharat 2047" — India's plan to be a developed nation.
   India-Pakistan nuclear standoff as a sign of regional power realignment.

6. THE GREAT DECEPTION / DAJJAL SYSTEM (Islamic eschatology + secular analysis)
   Prophecy: Before end times, a system of mass deception will control information and
   perception. Modern: AI deepfakes (show examples), social media manipulation, the fact that
   in 2026 you literally cannot trust video/audio evidence. 80% of Indians now use WhatsApp
   as their news source. The prophecy says "those with one eye" — single-perspective media.
   CONNECT: OpenAI, Meta, Google controlling what billions see.

7. THE ARMIES GATHERING (Multiple traditions — Islamic, Biblical, Hindu Kalki prophecy)
   Prophecy: A time when armies of nations will gather and the world will be at a crossroads.
   Modern: NATO expansion, Russia-Ukraine war year 4, China's military buildup, India's
   defence budget at all-time high ($75B in 2026), US-Iran tensions. The world has more
   active military conflicts right now than at any point since WW2.
   CLOSING SHOCK: India, with the world's second-largest army, sits at the center of all
   three major conflict zones — Middle East, China, Pakistan.

OUTRO (1 segment):
End with: "Whether you believe these are prophecies or patterns — the facts on the ground
are undeniable. The world is at an inflection point. What comes next will define the next
century. If this video made you think — share it with someone who needs to see it.
Because the truth is rarely trending."

PRODUCTION NOTES:
- Use real statistics (GDP figures, refugee counts, satellite data, military budgets)
- Each prophecy needs an original Arabic/Hebrew/Sanskrit quote — even a transliteration
- Strong visual_keyword for each segment (searchable Pexels terms)
- Tags must include: prophecy 2026, end times signs, islamic prophecy, india 2026,
  biblical prophecy, signs of judgement day, ancient predictions, world war 3 signs,
  Gaza prophecy, India superpower

THUMBNAIL TEXT: "7 SIGNS THE END HAS BEGUN" with subtitle "2026 — SEE THE PROOF"
"""

if __name__ == "__main__":
    init_db()
    vid_id = run(TOPIC, guidance=GUIDANCE, shorts_count=2)
    print(f"\nDONE — YouTube ID: {vid_id}", file=sys.stderr)
    sys.stderr.flush()
