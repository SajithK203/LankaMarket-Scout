"""
collector/cleaner.py
--------------------
Stage 2 of the pipeline: clean and deduplicate raw news items.

Steps:
  1. Strip HTML tags from headlines
  2. Normalise Unicode to NFC (so same Sinhala/Tamil word always compares equal)
  3. Detect and skip legacy Sinhala font text (looks like random Latin letters)
  4. Remove duplicate links
  5. Remove near-duplicate headlines (same story, different outlets)
"""

import re
import unicodedata
from difflib import SequenceMatcher


# ── HTML Stripping ────────────────────────────────────────────────────────────

_HTML_TAG = re.compile(r"<[^>]+>")

def strip_html(text: str) -> str:
    return _HTML_TAG.sub("", text).strip()


# ── Unicode Normalisation ─────────────────────────────────────────────────────

def normalise_unicode(text: str) -> str:
    """
    Convert to NFC so that the same Sinhala/Tamil character
    is always represented identically, regardless of how the
    source website encoded it.
    """
    return unicodedata.normalize("NFC", text)


# ── Legacy Sinhala Font Detection ─────────────────────────────────────────────
#
# Old Sinhala websites used custom fonts (e.g. "Iskoola Pota" or proprietary ones)
# where Latin code points were mapped to Sinhala glyphs by the font.
# Without the font, the text looks like random Latin letters (e.g. "mdf,h fjkia").
#
# HOW TO DETECT:
# Real Sinhala Unicode text contains characters in the range U+0D80–U+0DFF.
# Legacy-font text contains mostly ASCII letters but looks "random" — no real words.
#
# Simple heuristic: if the text contains > 30% ASCII letters but 0 Sinhala Unicode
# characters, and the source language is "si", flag it as legacy font.

_SINHALA_RANGE = re.compile(r"[\u0D80-\u0DFF]")
_ASCII_LETTER = re.compile(r"[a-zA-Z]")

def is_legacy_sinhala_font(text: str, language: str) -> bool:
    """
    Returns True if this looks like legacy-encoded Sinhala text that
    we cannot read. Such items should be skipped entirely.
    """
    if language != "si":
        return False
    has_sinhala_unicode = bool(_SINHALA_RANGE.search(text))
    ascii_ratio = len(_ASCII_LETTER.findall(text)) / max(len(text), 1)
    return not has_sinhala_unicode and ascii_ratio > 0.4


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate(items: list[dict]) -> list[dict]:
    """
    Remove duplicate items.
    First pass: exact link match.
    Second pass: near-identical headlines from different outlets
                 (similarity > 0.85 = same story).
    """
    # Pass 1: exact links
    seen_links = set()
    unique = []
    for item in items:
        link = item["link"]
        if link not in seen_links:
            seen_links.add(link)
            unique.append(item)

    # Pass 2: near-duplicate headlines
    deduped = []
    for item in unique:
        h = item["headline"]
        is_dup = any(
            SequenceMatcher(None, h, existing["headline"]).ratio() > 0.85
            for existing in deduped
        )
        if not is_dup:
            deduped.append(item)

    return deduped


# ── Main clean function ───────────────────────────────────────────────────────

def clean_items(raw_items: list[dict]) -> list[dict]:
    """
    Apply all cleaning steps to a list of raw feed items.
    Returns only clean, unique items.
    """
    cleaned = []
    skipped_legacy = 0

    for item in raw_items:
        headline = strip_html(item["headline"])
        headline = normalise_unicode(headline)

        # Skip legacy Sinhala font text — we cannot use it
        if is_legacy_sinhala_font(headline, item["language"]):
            skipped_legacy += 1
            continue

        item["headline"] = headline
        cleaned.append(item)

    if skipped_legacy:
        print(f"  Skipped {skipped_legacy} items with legacy Sinhala font encoding")

    before = len(cleaned)
    cleaned = deduplicate(cleaned)
    print(f"  Deduplicated: {before} -> {len(cleaned)} items")

    return cleaned
