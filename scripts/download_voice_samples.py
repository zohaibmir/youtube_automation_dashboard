#!/usr/bin/env python3
"""
Test voice samples downloader.
Generates 2-minute test scripts in English, Hindi, Urdu, and Hinglish,
then downloads audio samples for all recommended voices.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
import edge_tts

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from voice_config import LANGUAGE_VOICES

# Test scripts (2 minutes each at normal speech rate = ~260-300 words)
TEST_SCRIPTS = {
    "english": """
Hello, this is a test of the English voice narration system. 
We are testing all available Edge TTS voices for English to help you choose the best voice for your YouTube content.
This particular voice is being used to demonstrate crystal clear pronunciation and professional narration quality.
You will notice the natural intonation, proper emphasis on keywords, and smooth transitions between sentences.
The audio quality is studio-grade, perfect for geopolitical analysis, news commentary, and educational content.
This voice works exceptionally well for technical explanations and topics requiring authority and credibility.
Whether you're creating short-form content for YouTube Shorts or longer deep-dive videos, this voice adapts well.
The speech rate is adjustable, allowing you to slow down for complex topics or speed up for teasers.
All voices in our system support multiple accents and regional variants of English.
Thank you for listening to this English voice sample. We hope it meets your content creation needs.
""",
    "hindi": """
नमस्ते, यह हिंदी भाषा में वॉयस नैरेशन सिस्टम का परीक्षण है।
हम सभी उपलब्ध Edge TTS वॉयस को हिंदी में परीक्षण कर रहे हैं ताकि आप अपनी YouTube सामग्री के लिए सर्वश्रेष्ठ वॉयस चुन सकें।
इस विशेष वॉयस का उपयोग स्पष्ट उच्चारण और पेशेवर नैरेशन गुणवत्ता को प्रदर्शित करने के लिए किया जा रहा है।
आप प्राकृतिक स्वर, मुख्य शब्दों पर उचित जोर, और वाक्यों के बीच सुचारु संक्रमण देखेंगे।
ऑडियो गुणवत्ता स्टूडियो-दर्जे की है, जो भारतीय राजनीति, समाचार टिप्पणी और शैक्षणिक सामग्री के लिए उपयुक्त है।
यह वॉयस तकनीकी व्याख्या और विश्वासयोग्यता की आवश्यकता वाले विषयों के लिए असाधारण रूप से अच्छी तरह काम करता है।
YouTube Shorts के लिए लघु फॉर्म सामग्री से लेकर लंबी गहन वीडियो तक, यह वॉयस अच्छी तरह अनुकूल होता है।
भाषण दर समायोजन योग्य है, जो आपको जटिल विषयों के लिए धीमा करने या टीजर्स के लिए तेजी लाने की अनुमति देता है।
हमारी प्रणाली में सभी वॉयस हिंदी के कई बोलियों और क्षेत्रीय वेरिएंट का समर्थन करते हैं।
इस हिंदी वॉयस नमूने को सुनने के लिए धन्यवाद। हमें उम्मीद है कि यह आपकी सामग्री निर्माण आवश्यकताओं को पूरा करेगा।
""",
    "urdu": """
السلام علیکم، یہ اردو زبان میں وائس نیریشن سسٹم کا ٹیسٹ ہے۔
ہم تمام دستیاب Edge TTS وائسز کو اردو میں ٹیسٹ کر رہے ہیں تاکہ آپ اپنے YouTube مواد کے لیے بہترین وائس منتخب کر سکیں۔
یہ خاص وائس واضح تلفظ اور پروفیشنل نیریشن کوالٹی کو ظاہر کرنے کے لیے استعمال کی جا رہی ہے۔
آپ قدرتی لہجے، اہم الفاظ پر مناسب زور، اور جملوں کے درمیان ہموار منتقلی دیکھیں گے۔
آڈیو کوالٹی اسٹوڈیو گریڈ ہے، جو پاکستانی سیاست، خبروں کی تبصریوں اور تعلیمی مواد کے لیے موزوں ہے۔
یہ وائس تکنیکی تشریح اور سچائی کی ضرورت والے موضوعات کے لیے بہترین طریقے سے کام کرتا ہے۔
YouTube Shorts کے لیے مختصر فارمیٹ سے لے کر گہری تفصیل والی ویڈیوز تک، یہ وائس اچھی طرح موافق ہوتا ہے۔
بولنے کی رفتار قابل تبدیلی ہے، جو آپ کو پیچیدہ موضوعات کے لیے سست کر سکتی ہے یا ٹیزرز کے لیے تیز کر سکتی ہے۔
ہمارے سسٹم میں تمام وائسز اردو کی متعدد بولیوں اور علاقائی متغیرات کی حمایت کرتے ہیں۔
اس اردو وائس نمونے کو سننے کے لیے شکریہ۔ ہمیں امید ہے کہ یہ آپ کی مواد سازی کی ضروریات کو پورا کرے گا۔
""",
    "hinglish": """
Hello dost, yeh Hinglish voice narration system ka test hai jo English aur Hindi dono bhasha ko combine karta hai.
Hum sab available Edge TTS voices ko Hinglish mein test kar rahe hain taaki aap ka YouTube content aur attractive bane.
Yeh special voice clear pronunciation aur professional narration quality ko demonstrate kar raha hai.
Aap dekhenge natural intonation, keywords par proper emphasis, aur sentences ke beech smooth transitions ka.
Audio quality studio-grade hai, jo Indian geopolitics, politics, aur educational content ke liye perfect hai.
Yeh voice technical explanations aur credibility ki zaroorat wale topics ke liye bilkul amazing hai.
YouTube Shorts ke liye short-form content se lekar deep-dive videos tak, yeh voice sab mein adapt karta hai.
Speech rate adjustable hai, jo aapko complex topics ke liye slow karne ya teasers ke liye fast karne deta hai.
Hamaare system mein sab voices Hindi ke multiple dialects aur English variants ko support karte hain.
Iska matlab aap Hindi speakers aur English speakers dono ko same content se engage kar sakte ho.
Hinglish bahut popular hai India mein, aur yeh voice production bilkul natural lagta hai.
Is Hinglish voice sample ko sunne ke liye shukriya. Hume hope hai yeh aapki content creation needs ko pura karega.
"""
}

VOICES_DIR = Path(__file__).parent / "voice_samples"


async def download_voice_sample(voice_id: str, text: str, lang: str, voice_name: str):
    """Download and save a voice sample."""
    VOICES_DIR.mkdir(exist_ok=True)
    
    # Sanitize filename
    safe_name = voice_name.replace(" ", "_").replace("(", "").replace(")", "")
    output_path = VOICES_DIR / f"{lang}_{voice_id}_{safe_name}.mp3"
    
    if output_path.exists():
        print(f"✓ Already exists: {output_path.name}")
        return
    
    try:
        print(f"⏳ Downloading: {lang.upper()} - {voice_name}...", end=" ")
        communicate = edge_tts.Communicate(text, voice_id)
        await communicate.save(output_path)
        print(f"✓ Saved: {output_path.name}")
    except Exception as e:
        print(f"✗ Failed: {str(e)}")


async def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       Voice Samples Downloader - All Languages           ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    
    tasks = []
    
    for lang, config in LANGUAGE_VOICES.items():
        text = TEST_SCRIPTS.get(lang, TEST_SCRIPTS["english"])
        print(f"\n📝 Downloading {config['label']} voices ({len(config['recommended'])} voices)...")
        
        for voice_config in config['recommended']:
            voice_id = voice_config['id']
            voice_name = voice_config['name']
            task = download_voice_sample(voice_id, text, lang, voice_name)
            tasks.append(task)
    
    # Download all concurrently with rate limiting
    for i in range(0, len(tasks), 3):
        batch = tasks[i:i+3]
        await asyncio.gather(*batch)
        if i + 3 < len(tasks):
            print("  (pausing 2 seconds to avoid rate limits...)")
            await asyncio.sleep(2)
    
    print(f"\n✓ All voice samples saved to: {VOICES_DIR}")
    print(f"  Total files: {len(list(VOICES_DIR.glob('*.mp3')))}")
    print("\nTo test locally:")
    print(f"  open {VOICES_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
