"""
collector/filter.py
-------------------
Stage 3+4 of the pipeline: language detection and keyword filter.

TWO jobs in one file:

  Stage 3 — keep only business-relevant sections and detect language.
  Stage 4 — keyword screen: drop any headline that contains no business
             signal keyword before we spend money on an LLM call.

Order matters:
  clean_items()  →  detect_language()  →  section_filter()  →  keyword_filter()

Why keyword filter before LLM?
  Each LLM call costs money. A sports headline or entertainment story will
  never be business-relevant. Dropping those cheaply here means we only
  pay the LLM for items that are probably worth classifying.

Member A owns this file.
"""

import re
import unicodedata
from pathlib import Path

import yaml

# ── Load keyword lists ────────────────────────────────────────────────────────

_KEYWORDS_PATH = Path("data/keywords/business_keywords.yaml")

def _load_keywords() -> list[str]:
    """Load all keywords from all three language sections into one flat list."""
    with open(_KEYWORDS_PATH, encoding="utf-8") as f:
        kw = yaml.safe_load(f)
    all_kw = []
    for lang_section in ("english", "sinhala", "tamil"):
        all_kw.extend(kw.get(lang_section, []))
    return all_kw

_KEYWORDS: list[str] = _load_keywords()


# ── Load language detection ───────────────────────────────────────────────────
# We try langdetect first (pure-Python, no binary model needed).
# If it is not installed we fall back to a simple Unicode-range heuristic.

def _try_import_langdetect():
    try:
        from langdetect import detect, LangDetectException
        return detect, LangDetectException
    except ImportError:
        return None, None

_langdetect_detect, _LangDetectException = _try_import_langdetect()

# Sinhala Unicode block: U+0D80–U+0DFF
_SINHALA_RE = re.compile(r"[\u0D80-\u0DFF]")
# Tamil Unicode block: U+0B80–U+0BFF
_TAMIL_RE   = re.compile(r"[\u0B80-\u0BFF]")


def detect_language(text: str) -> str:
    """
    Detect the primary language of a text string.
    Returns 'si' (Sinhala), 'ta' (Tamil), or 'en' (English / unknown).

    Strategy:
      1. If the text contains Sinhala Unicode characters → 'si'
      2. If the text contains Tamil Unicode characters   → 'ta'
      3. Otherwise use langdetect library if available.
      4. Fall back to 'en'.

    Unicode-range checks are fast and reliable for headlines that actually
    contain script characters. langdetect handles romanised or mixed text.
    """
    if _SINHALA_RE.search(text):
        return "si"
    if _TAMIL_RE.search(text):
        return "ta"

    if _langdetect_detect is not None:
        try:
            lang = _langdetect_detect(text)
            # langdetect codes: 'si', 'ta', 'en', etc.
            if lang in ("si", "ta", "en"):
                return lang
        except _LangDetectException:
            pass

    return "en"  # safe default


# ── Section filter ────────────────────────────────────────────────────────────

# Sections we always keep (even if they sound non-business — policy and tax
# news is often filed under "politics" or "local").
_KEEP_SECTIONS = {
    "business", "economy", "finance", "international",
    "technology", "politics", "local", "general",
    "agriculture", "trade", "news",
}

# Sections we always drop immediately — no business signal.
_DROP_SECTIONS = {
    "sport", "sports", "entertainment", "lifestyle",
    "celebrity", "gossip", "fashion", "food-entertainment",
}


def section_filter(items: list[dict]) -> list[dict]:
    """
    Keep items from business-relevant sections; drop sports and entertainment.
    Items with an unknown/missing section are kept (conservative: don't drop
    things we are unsure about — the keyword filter will handle them).
    """
    kept = []
    dropped = 0
    for item in items:
        section = item.get("section", "general").lower().strip()
        if section in _DROP_SECTIONS:
            dropped += 1
            continue
        kept.append(item)

    if dropped:
        print(f"  Section filter: dropped {dropped} sport/entertainment items")
    return kept


# ── Keyword filter ────────────────────────────────────────────────────────────

def _normalise_for_match(text: str) -> str:
    """Lower-case and NFC-normalise so Unicode keywords compare correctly."""
    return unicodedata.normalize("NFC", text).lower()


def has_business_keyword(headline: str) -> bool:
    """
    Return True if the headline contains at least one keyword from the
    business keyword list (any language).

    Matching is case-insensitive and Unicode-normalised so Sinhala and Tamil
    keywords match correctly regardless of minor encoding differences.
    """
    h = _normalise_for_match(headline)
    return any(_normalise_for_match(kw) in h for kw in _KEYWORDS)


def keyword_filter(items: list[dict]) -> list[dict]:
    """
    Stage 4: drop items that contain no business keyword.
    Returns only items likely worth sending to the LLM.

    Logs how many were kept vs dropped so Member A can monitor filter quality.
    """
    before = len(items)
    kept = [item for item in items if has_business_keyword(item["headline"])]
    dropped = before - len(kept)
    pct = int((len(kept) / before * 100)) if before else 0
    print(f"  Keyword filter: {before} → {len(kept)} items kept ({pct}%), {dropped} dropped")
    return kept


# ── Language tagging ──────────────────────────────────────────────────────────

def tag_languages(items: list[dict]) -> list[dict]:
    """
    For items where the source YAML declared a language, trust that.
    For items with language='unknown' or missing, detect from headline text.
    Returns the same list with 'language' field set on every item.
    """
    for item in items:
        declared = item.get("language", "").strip().lower()
        if declared in ("si", "ta", "en"):
            continue  # trust the sources.yaml declaration
        # detect from text
        item["language"] = detect_language(item.get("headline", ""))
    return items


# ── Combined pipeline stage ───────────────────────────────────────────────────

def apply_filters(items: list[dict]) -> list[dict]:
    """
    Run all Stage 3+4 filters in order:
      1. Tag / verify language
      2. Section filter (drop sports/entertainment immediately)
      3. Keyword filter (drop non-business headlines cheaply)

    Returns only items ready to be sent to the LLM extractor.
    """
    items = tag_languages(items)
    items = section_filter(items)
    items = keyword_filter(items)
    return items


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        {"headline": "Fuel prices increased by Rs. 50 per litre", "language": "en", "section": "business"},
        {"headline": "Colombo team wins cricket match by 6 wickets", "language": "en", "section": "sports"},
        {"headline": "ඉන්ධන මිල ඉහළ යයි — ලිට්රයක් රු. 50 කින් වැඩිවෙයි", "language": "si", "section": "general"},
        {"headline": "New road construction in Kandy begins", "language": "en", "section": "local"},
        {"headline": "Celebrity gossip from the weekend", "language": "en", "section": "entertainment"},
        {"headline": "விலை உயர்வு: எரிபொருள் லிட்டர் ரூ. 50 அதிகமானது", "language": "ta", "section": "general"},
    ]

    print("=== Filter test ===")
    result = apply_filters(samples)
    print(f"\nIn: {len(samples)} | Out: {len(result)}")
    for item in result:
        print(f"  [{item['language']}] {item['headline'][:70]}")
