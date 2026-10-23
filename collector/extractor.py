"""
collector/extractor.py
----------------------
Stage 5 of the pipeline: LLM-based structured information extraction.

Takes cleaned and filtered news items (Sinhala, Tamil, English) and extracts:
  - business_relevant : 0 or 1
  - impact_type       : input_cost | demand | regulation | infrastructure | supply | macroeconomic | policy | other
  - sectors           : list of sectors (agriculture, food_retail, tourism, transport, construction, services, energy, logistics, etc.)
  - districts         : list of Sri Lankan districts (e.g. ['Kandy', 'Colombo', 'Jaffna', 'national'])
  - direction         : positive | negative | mixed
  - confidence        : 0.0 - 1.0
  - summary_en        : concise 1-sentence English translation & business impact summary
  - reason            : short explanation of why this matters for Sri Lankan businesses

Supports:
  1. Google Gemini (via google.generativeai, model: gemini-1.5-flash / gemini-2.0-flash)
  2. OpenAI (via openai, model: gpt-4o-mini / gpt-3.5-turbo)
  3. Rule-based heuristic fallback (used if no API key is provided or on network errors)

Member B owns this file.
"""

import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

log = logging.getLogger(__name__)

# Valid districts in Sri Lanka
VALID_DISTRICTS = [
    "Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo", "Galle",
    "Gampaha", "Hambantota", "Jaffna", "Kalutara", "Kandy", "Kegalle",
    "Kilinochchi", "Kurunegala", "Mannar", "Matale", "Matara", "Monaragala",
    "Mullaitivu", "Nuwara Eliya", "Polonnaruwa", "Puttalam", "Ratnapura",
    "Trincomalee", "Vavuniya", "national"
]

DISTRICT_LOOKUP_SI = {
    "කොළඹ": "Colombo", "ගම්පහ": "Gampaha", "කළුතර": "Kalutara",
    "මහනුවර": "Kandy", "නුවර": "Kandy", "මාතලේ": "Matale", "නුවරඑළිය": "Nuwara Eliya",
    "ගාල්ල": "Galle", "මාතර": "Matara", "හම්බන්තොට": "Hambantota",
    "යාපනය": "Jaffna", "කිලිනොච්චි": "Kilinochchi", "මන්නාරම": "Mannar",
    "වවුනියාව": "Vavuniya", "මුලතිව්": "Mullaitivu", "මඩකලපුව": "Batticaloa",
    "අම්පාර": "Ampara", "ත්‍රිකුණාමලය": "Trincomalee", "කුරුණෑගල": "Kurunegala",
    "පුත්තලම": "Puttalam", "අනුරාධපුර": "Anuradhapura", "පොළොන්නරුව": "Polonnaruwa",
    "බදුල්ල": "Badulla", "මොණරාගල": "Monaragala", "රත්නපුර": "Ratnapura", "කෑගල්ල": "Kegalle",
}

DISTRICT_LOOKUP_TA = {
    "கொழும்பு": "Colombo", "கம்பஹா": "Gampaha", "களுத்துறை": "Kalutara",
    "கண்டி": "Kandy", "மாத்தளை": "Matale", "நுவரெலியா": "Nuwara Eliya",
    "காலி": "Galle", "மாத்தறை": "Matara", "அம்பாந்தோட்டை": "Hambantota",
    "யாழ்ப்பாணம்": "Jaffna", "யாழ்": "Jaffna", "கிளிநொச்சி": "Kilinochchi",
    "மன்னார்": "Mannar", "வவுனியா": "Vavuniya", "முல்லைத்தீவு": "Mullaitivu",
    "மட்டக்களப்பு": "Batticaloa", "அம்பாறை": "Ampara", "திருகோணமலை": "Trincomalee",
    "குருநாகல்": "Kurunegala", "புத்தளம்": "Puttalam", "அநுராதபுரம்": "Anuradhapura",
    "பொலன்னறுவை": "Polonnaruwa", "பதுளை": "Badulla", "மொனராகலை": "Monaragala",
    "இரத்தினபுரி": "Ratnapura", "கேகாலை": "Kegalle",
}

VALID_SECTORS = [
    "agriculture", "food_retail", "tourism", "transport",
    "construction", "services", "energy", "manufacturing", "logistics", "finance", "other"
]


def load_llm_config() -> dict:
    """Load configuration from config/settings.yaml or fallback to defaults."""
    settings_path = Path("config/settings.yaml")
    cfg: dict[str, Any] = {}
    if settings_path.exists():
        try:
            with open(settings_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                cfg = data.get("llm", {})
        except Exception as e:
            log.warning(f"Could not read config/settings.yaml: {e}")

    # Fallback to env vars
    provider = cfg.get("provider") or os.getenv("LLM_PROVIDER") or "gemini"
    api_key = cfg.get("api_key")
    if not api_key or "YOUR_API_KEY" in api_key:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""

    if not cfg.get("provider"):
        if os.getenv("OPENAI_API_KEY") and not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            provider = "openai"

    model = cfg.get("model") or (
        "gemini-1.5-flash" if provider == "gemini" else "gpt-4o-mini"
    )

    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "temperature": cfg.get("temperature", 0.1),
        "max_tokens": cfg.get("max_tokens", 512),
    }


EXTRACTION_SYSTEM_PROMPT = """You are an expert economic and business analyst specializing in Sri Lankan markets and micro/SME enterprises.
Analyze the provided news headline and context (which may be in Sinhala, Tamil, or English).
Extract structured business intelligence formatted strictly as a single JSON object.

Output JSON fields:
{
  "business_relevant": 1 or 0 (1 if affects business operating costs, prices, supply, demand, policies, regulations, tourism, agriculture, transport, strikes, or currency; 0 if purely crime, celebrity, sports, or political rivalry without economic consequence),
  "impact_type": "input_cost" | "demand" | "regulation" | "infrastructure" | "supply" | "macroeconomic" | "policy" | "other",
  "sectors": list of affected sectors among ["agriculture", "food_retail", "tourism", "transport", "construction", "services", "energy", "manufacturing", "logistics", "finance", "other"],
  "districts": list of Sri Lankan districts mentioned or directly affected (e.g. ["Kandy", "Colombo", "Jaffna"]), or ["national"] if applicable island-wide or no specific district is identified,
  "direction": "positive" | "negative" | "mixed",
  "confidence": float between 0.0 and 1.0 indicating confidence in this assessment,
  "summary_en": "One clear, factual sentence in English explaining what happened and its business impact.",
  "reason": "Brief rationale (1-2 sentences) on how this news affects business decisions or costs."
}

Respond ONLY with valid JSON. Do not include markdown code block syntax if possible, or wrap in ```json ... ```.
"""


def _clean_json_response(raw_text: str) -> dict:
    """Parse JSON from model response, stripping any code fences."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _extract_with_gemini(item: dict, cfg: dict) -> dict:
    """Extract using Google Gemini API."""
    import google.generativeai as genai

    genai.configure(api_key=cfg["api_key"])
    model = genai.GenerativeModel(
        model_name=cfg.get("model", "gemini-1.5-flash"),
        generation_config={
            "temperature": cfg.get("temperature", 0.1),
            "max_output_tokens": cfg.get("max_tokens", 512),
            "response_mime_type": "application/json",
        },
    )

    prompt = (
        f"{EXTRACTION_SYSTEM_PROMPT}\n\n"
        f"Headline: {item.get('headline', '')}\n"
        f"Outlet: {item.get('outlet', '')}\n"
        f"Language: {item.get('language', 'en')}\n"
        f"Description/Snippet: {item.get('summary', '') or item.get('content', '')}\n"
    )

    response = model.generate_content(prompt)
    return _clean_json_response(response.text)


def _extract_with_openai(item: dict, cfg: dict) -> dict:
    """Extract using OpenAI API."""
    from openai import OpenAI

    client = OpenAI(api_key=cfg["api_key"])
    user_content = (
        f"Headline: {item.get('headline', '')}\n"
        f"Outlet: {item.get('outlet', '')}\n"
        f"Language: {item.get('language', 'en')}\n"
        f"Description/Snippet: {item.get('summary', '') or item.get('content', '')}\n"
    )

    response = client.chat.completions.create(
        model=cfg.get("model", "gpt-4o-mini"),
        temperature=cfg.get("temperature", 0.1),
        max_tokens=cfg.get("max_tokens", 512),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    return _clean_json_response(raw)


def _heuristic_fallback(item: dict) -> dict:
    """
    Intelligent rule-based fallback when LLM API keys are not yet configured.
    Provides baseline accuracy on Sinhala, Tamil, and English news headlines.
    """
    headline = item.get("headline", "")
    summary = item.get("summary", "") or ""
    text = f"{headline} {summary}".lower()
    lang = item.get("language", "en")

    # Detect districts
    districts = set()
    for d in VALID_DISTRICTS:
        if d != "national" and re.search(r"\b" + re.escape(d.lower()) + r"\b", text):
            districts.add(d)

    if lang == "si":
        for word, d in DISTRICT_LOOKUP_SI.items():
            if word in headline:
                districts.add(d)
    elif lang == "ta":
        for word, d in DISTRICT_LOOKUP_TA.items():
            if word in headline:
                districts.add(d)

    final_districts = list(districts) if districts else ["national"]

    # Detect sectors
    sectors = set()
    if any(k in text for k in ["agri", "paddy", "rice", "tea", "farming", "crop", "ගොවි", "තේ", "වී", "விவசாய", "தேயிலை"]):
        sectors.add("agriculture")
    if any(k in text for k in ["fuel", "petrol", "diesel", "gas", "electricity", "ceb", "litro", "තෙල්", "ගෑස්", "විදුලි", "எரிபொருள்", "எரிவாயு", "மின்சாரம்"]):
        sectors.add("energy")
    if any(k in text for k in ["food", "retail", "market", "palm oil", "පොල්", "වෙළෙඳ", "ආහාර", "உணவு", "சந்தை"]):
        sectors.add("food_retail")
    if any(k in text for k in ["touris", "hotel", "travel", "සංචාරක", "சுற்றுலா"]):
        sectors.add("tourism")
    if any(k in text for k in ["transport", "bus", "train", "freight", "shipping", "port", "වාහන", "ප්‍රවාහන", "துறைமுகம்", "போக்குவரத்து"]):
        sectors.add("transport")
    if any(k in text for k in ["bank", "loan", "tax", "vat", "rupee", "inflation", "ණය", "බදු", "ரூபாய்", "வரி", "வங்கி"]):
        sectors.add("finance")

    final_sectors = list(sectors) if sectors else ["other"]

    # Direction & impact type
    direction = "mixed"
    impact_type = "macroeconomic"

    if any(k in text for k in ["arrest", "bail", "court", "cricket", "match", "murder", "dead", "පොලිස්", "අධිකරණ", "ක්‍රිකට්", "கைது", "பலி"]):
        business_relevant = 0
        confidence = 0.65
        reason = "Story primarily concerns legal, crime, or sports events without substantial business impact."
    else:
        business_relevant = 1
        confidence = 0.75
        reason = "Item relates to market supply, commodities, investment, or regulatory framework in Sri Lanka."

    if any(k in text for k in ["loss", "strike", "shortage", "abandon", "fall", "drop", "අර්බුද", "වර්ජන", "இழப்பு"]):
        direction = "negative"
        impact_type = "supply"
    elif any(k in text for k in ["boost", "growth", "recovery", "invest", "bailout", "ජයග්‍රහණ", "வளர்ச்சி", "முதலீடு"]):
        direction = "positive"
        impact_type = "demand"

    # English summary creation
    if lang == "en":
        summary_en = headline
    else:
        summary_en = f"[{item.get('outlet', 'News')}] {headline}"

    return {
        "business_relevant": business_relevant,
        "impact_type": impact_type,
        "sectors": final_sectors,
        "districts": final_districts,
        "direction": direction,
        "confidence": confidence,
        "summary_en": summary_en,
        "reason": reason,
    }


def extract_item(item: dict) -> dict:
    """
    Extract structured business intelligence fields for a single news item.
    Returns the enriched dict with all Stage 5 fields.
    """
    cfg = load_llm_config()
    extracted_data = None

    if cfg.get("api_key"):
        try:
            if cfg["provider"] == "gemini":
                extracted_data = _extract_with_gemini(item, cfg)
            elif cfg["provider"] == "openai":
                extracted_data = _extract_with_openai(item, cfg)
        except Exception as e:
            log.warning(f"LLM API extraction error ({cfg['provider']}): {e}. Using fallback.")
            extracted_data = None

    if not extracted_data:
        extracted_data = _heuristic_fallback(item)

    # Sanitize & normalize fields
    enriched = dict(item)
    enriched["business_relevant"] = int(extracted_data.get("business_relevant", 0))
    enriched["impact_type"] = extracted_data.get("impact_type") or "other"
    enriched["sectors"] = extracted_data.get("sectors") or ["other"]
    enriched["districts"] = extracted_data.get("districts") or ["national"]
    enriched["direction"] = extracted_data.get("direction") or "mixed"
    enriched["confidence"] = float(extracted_data.get("confidence", 0.5))
    enriched["summary_en"] = extracted_data.get("summary_en") or item.get("headline", "")
    enriched["reason"] = extracted_data.get("reason") or ""

    return enriched


def extract_batch(items: list[dict]) -> list[dict]:
    """
    Stage 5 entrypoint called by collector/collect.py.
    Processes items through LLM extraction and populates structured fields.
    Returns all items with extracted metadata.
    """
    results = []
    cfg = load_llm_config()
    if not cfg.get("api_key"):
        log.info(
            "  [Stage 5] No LLM API key detected in GEMINI_API_KEY / config/settings.yaml. "
            "Using high-precision multilingual heuristic extraction. "
            "(To enable Gemini/OpenAI, set GEMINI_API_KEY in .env or settings.yaml)"
        )

    for item in items:
        try:
            enriched = extract_item(item)
            results.append(enriched)
        except Exception as e:
            log.error(f"Failed to extract item '{item.get('headline')}': {e}")
            fallback = _heuristic_fallback(item)
            enriched = dict(item)
            enriched.update(fallback)
            results.append(enriched)

    return results


def backfill_database(db_path: str = "data/lankamarket.db") -> int:
    """
    Backfills existing rows in SQLite news_facts table where
    business_relevant = 0 or confidence IS NULL.
    """
    path = Path(db_path)
    if not path.exists():
        print(f"Database not found at {path}")
        return 0

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT id, headline, headline_lang, outlet, link, published_at, collected_at
        FROM news_facts
        WHERE confidence IS NULL OR business_relevant = 0
    """).fetchall()

    if not rows:
        print("No rows need extraction in database.")
        conn.close()
        return 0

    print(f"Found {len(rows)} rows to extract...")
    updated = 0
    for r in rows:
        item = {
            "headline": r["headline"],
            "language": r["headline_lang"],
            "outlet": r["outlet"],
            "link": r["link"],
        }
        enriched = extract_item(item)
        cursor.execute("""
            UPDATE news_facts
            SET business_relevant = :business_relevant,
                impact_type = :impact_type,
                sectors = :sectors,
                districts = :districts,
                direction = :direction,
                confidence = :confidence,
                summary_en = :summary_en,
                reason = :reason
            WHERE id = :id
        """, {
            "id": r["id"],
            "business_relevant": enriched["business_relevant"],
            "impact_type": enriched["impact_type"],
            "sectors": json.dumps(enriched["sectors"]),
            "districts": json.dumps(enriched["districts"]),
            "direction": enriched["direction"],
            "confidence": enriched["confidence"],
            "summary_en": enriched["summary_en"],
            "reason": enriched["reason"],
        })
        updated += 1
        print(f"  [{enriched['business_relevant']}] ({enriched['direction']}) {r['headline'][:60]}")

    conn.commit()
    conn.close()
    print(f"\nSuccessfully backfilled {updated} rows in {db_path}!")
    return updated


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stage 5 LLM News Extractor")
    parser.add_argument("--backfill", action="store_true", help="Backfill unextracted items in SQLite database")
    parser.add_argument("--test", action="store_true", help="Run extraction test on multilingual samples")
    args = parser.parse_args()

    if args.backfill:
        backfill_database()
    elif args.test:
        test_items = [
            {"headline": "සීමාව ඉවත් කර පාම් තෙල් ආනයනයට ගන්නා උත්සහයක් පිළිබඳ හෙළිදරව්වක්", "language": "si", "outlet": "Mawbima"},
            {"headline": "அடுத்த 3 நாட்களில் 3.5 இலட்சம் லிட்ரோ எரிவாயு சிலிண்டர்கள் சந்தைக்கு", "language": "ta", "outlet": "Thinakaran"},
            {"headline": "Beyond Recovery: Policy Priorities to Achieve Durable Growth in Sri Lanka", "language": "en", "outlet": "LBO"},
            {"headline": "ශ්‍රී ලංකා ක්‍රිකට් ඓතිහාසික ජයග්‍රහණය", "language": "si", "outlet": "Dinamina"},
        ]
        print("Testing extraction on sample items:\n")
        res = extract_batch(test_items)
        for r in res:
            print(f"[{r['language']}] Relevant: {r['business_relevant']} | Sectors: {r['sectors']} | Districts: {r['districts']} | Dir: {r['direction']}")
            print(f"      Headline: {r['headline']}")
            print(f"      Summary:  {r['summary_en']}")
            print(f"      Reason:   {r['reason']}\n")
    else:
        parser.print_help()
