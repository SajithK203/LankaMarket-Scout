"""
collector/collect.py
--------------------
Stages 1 → 4 of the LankaMarket Scout pipeline:

  Stage 1  COLLECT    — fetch RSS feeds from sources.yaml
  Stage 2  CLEAN      — strip HTML, normalise Unicode, detect legacy Sinhala font
  Stage 3  DEDUPLICATE— remove exact-link and near-headline duplicates
  Stage 4  FILTER     — tag language, drop non-business sections, keyword screen

Stage 5 (LLM extraction) is called here too when collector/extractor.py exists.
If it is not yet available the items are saved with business_relevant=0 and
Member B wires it in later.

Run:
    python -m collector.collect --dry-run    # fetch, clean, filter — do not save
    python -m collector.collect              # full run, saves to DB
    python -m collector.collect --lang si    # only Sinhala feeds
    python -m collector.collect --lang ta    # only Tamil feeds
    python -m collector.collect --lang en    # only English feeds

Member A owns this file.
"""

import argparse
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
import yaml

from collector.cleaner import clean_items
from collector.filter import apply_filters

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

SOURCES_PATH = Path("data/feeds/sources.yaml")
REQUEST_DELAY = 3       # seconds between requests — be polite
USER_AGENT    = "LankaMarketScout/0.1 (research prototype; open source)"


# ── Source loading ────────────────────────────────────────────────────────────

def load_sources(path: Path, lang_filter: str | None = None) -> list[dict]:
    """
    Load feed list from sources.yaml.
    Skips entries with no URL and entries marked status='skip'.
    Optional lang_filter: 'si' | 'ta' | 'en' — only load that language.
    """
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sources = config.get("sources", [])
    sources = [s for s in sources if s.get("url") and s.get("status") != "skip"]

    if lang_filter:
        sources = [s for s in sources if s.get("language") == lang_filter]

    log.info(f"Loaded {len(sources)} sources from {path}"
             + (f" (language={lang_filter})" if lang_filter else ""))
    return sources


# ── robots.txt check ─────────────────────────────────────────────────────────

def check_robots(base_url: str) -> bool:
    """
    Check robots.txt before fetching.  Returns True = OK to proceed.

    We use a simple heuristic: if robots.txt exists and contains 'Disallow: /'
    (block everything) we skip.  A proper implementation would use Python's
    stdlib urllib.robotparser — upgrade this if needed.

    We always identify ourselves honestly with USER_AGENT.
    """
    robots_url = base_url.rstrip("/") + "/robots.txt"
    try:
        resp = requests.get(
            robots_url, timeout=5,
            headers={"User-Agent": USER_AGENT}
        )
        if resp.status_code == 200:
            # Look for "Disallow: /" which blocks all crawlers
            for line in resp.text.splitlines():
                line = line.strip()
                if line.lower().startswith("disallow:") and line.split(":", 1)[1].strip() == "/":
                    log.warning(f"robots.txt blocks all: {robots_url}")
                    return False
    except Exception:
        pass  # Unreachable robots.txt → proceed (conservative, but allows orphan sites)
    return True


# ── Feed fetching ─────────────────────────────────────────────────────────────

def fetch_feed(source: dict) -> list[dict]:
    """
    Fetch one RSS/Atom feed and return a list of raw item dicts.

    Each returned item has these keys (used by downstream stages):
        headline, link, published, outlet, language, section, collected_at
    """
    url      = source["url"]
    outlet   = source["name"]
    language = source.get("language", "en")
    section  = source.get("section", "general")

    headers = {
        "User-Agent":      USER_AGENT,
        "Accept-Language": "si, ta, en",
    }

    try:
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except requests.exceptions.HTTPError as e:
        log.error(f"  {outlet}: HTTP error — {e}")
        return []
    except requests.exceptions.Timeout:
        log.error(f"  {outlet}: timed out after 12 s")
        return []
    except Exception as e:
        log.error(f"  {outlet}: fetch failed — {e}")
        return []

    collected_at = datetime.now(timezone.utc).isoformat()

    items = []
    for entry in feed.entries:
        headline  = (entry.get("title") or "").strip()
        link      = (entry.get("link")  or "").strip()
        published = entry.get("published") or entry.get("updated") or ""

        if not headline or not link:
            continue

        items.append({
            "headline":     headline,
            "link":         link,
            "published":    published,
            "outlet":       outlet,
            "language":     language,
            "section":      section,
            "collected_at": collected_at,
        })

    log.info(f"  {outlet}: {len(items)} items fetched")
    return items


# ── LLM extraction (Stage 5) — optional ──────────────────────────────────────

def _try_extract(items: list[dict]) -> list[dict]:
    """
    Attempt Stage 5 LLM extraction.  If collector/extractor.py does not exist
    yet (Member B hasn't written it), we gracefully skip and save the items
    with business_relevant=0 so the pipeline still works.

    Returns items with LLM fields filled, or original items unchanged.
    """
    try:
        from collector.extractor import extract_batch  # type: ignore
        log.info(f"  Running LLM extraction on {len(items)} items...")
        extracted = extract_batch(items)
        log.info(f"  Extraction done: {len(extracted)} business-relevant items")
        return extracted
    except ImportError:
        log.info("  collector/extractor.py not found — skipping Stage 5 (LLM extraction)")
        log.info("  Items saved with business_relevant=0; run extractor later.")
        return items


# ── Database save ─────────────────────────────────────────────────────────────

def save_to_db(items: list[dict]) -> int:
    """
    Save a list of pipeline-processed items to the SQLite database.
    Returns the count of newly inserted rows (duplicates are silently skipped).
    """
    from database.db import get_connection, create_tables, save_item

    conn = get_connection()
    create_tables(conn)

    saved = 0
    for item in items:
        row = {
            "headline":          item["headline"],
            "headline_lang":     item.get("language", "en"),
            "outlet":            item["outlet"],
            "link":              item["link"],
            "published_at":      item.get("published", ""),
            "collected_at":      item.get("collected_at", datetime.now(timezone.utc).isoformat()),
            # LLM-filled fields (Stage 5) — defaults used when extractor not available
            "business_relevant": int(item.get("business_relevant", 0)),
            "impact_type":       item.get("impact_type"),
            "sectors":           item.get("sectors", []),
            "districts":         item.get("districts", []),
            "direction":         item.get("direction"),
            "confidence":        item.get("confidence"),
            "summary_en":        item.get("summary_en"),
            "reason":            item.get("reason"),
        }
        if save_item(conn, row):
            saved += 1

    conn.close()
    return saved


# ── Health summary ────────────────────────────────────────────────────────────

def print_health_summary(source_results: list[dict]) -> None:
    """
    Print a concise table of which sources worked and how many items
    each contributed.  Copy this into docs/status.md as the daily feed report.
    """
    print("\n" + "=" * 72)
    print("FEED HEALTH SUMMARY")
    print("=" * 72)
    print(f"{'Outlet':<28} {'Lang':<6} {'Fetched':>8} {'After filter':>13}")
    print("-" * 72)
    total_fetched  = 0
    total_filtered = 0
    for r in source_results:
        print(
            f"{r['outlet']:<28} {r['language']:<6} "
            f"{r['fetched']:>8} {r['after_filter']:>13}"
        )
        total_fetched  += r["fetched"]
        total_filtered += r["after_filter"]
    print("-" * 72)
    print(f"{'TOTAL':<28} {'':6} {total_fetched:>8} {total_filtered:>13}")
    print("=" * 72 + "\n")


# ── Main collection function ──────────────────────────────────────────────────

def collect_all(dry_run: bool = False, lang_filter: str | None = None) -> list[dict]:
    """
    Run the full Stages 1–4 pipeline (+ optional Stage 5) for all sources.

    dry_run=True  → fetch, clean, filter and print — do NOT save to DB.
                    Use this to test feeds without touching the database.
    lang_filter   → 'si' | 'ta' | 'en' | None (all).
    """
    sources = load_sources(SOURCES_PATH, lang_filter=lang_filter)
    if not sources:
        log.warning("No sources to collect.  Check sources.yaml and --lang flag.")
        return []

    all_raw: list[dict] = []
    source_results: list[dict] = []

    # ── Stage 1: COLLECT ─────────────────────────────────────────────────────
    for source in sources:
        base_url = f"{urlparse(source['url']).scheme}://{urlparse(source['url']).netloc}"

        if not check_robots(base_url):
            log.warning(f"Skipping {source['name']} — robots.txt check failed")
            source_results.append({
                "outlet":       source["name"],
                "language":     source.get("language", "?"),
                "fetched":      0,
                "after_filter": 0,
            })
            time.sleep(REQUEST_DELAY)
            continue

        raw_items = fetch_feed(source)
        all_raw.extend(raw_items)

        source_results.append({
            "outlet":       source["name"],
            "language":     source.get("language", "?"),
            "fetched":      len(raw_items),
            "after_filter": 0,  # filled in below after filtering
        })

        time.sleep(REQUEST_DELAY)  # polite pause between sites

    log.info(f"Stage 1 complete: {len(all_raw)} raw items from {len(sources)} sources")

    if not all_raw:
        log.warning("No items fetched — check network, feed URLs and robots.txt results.")
        return []

    # ── Stage 2+3: CLEAN + DEDUPLICATE ───────────────────────────────────────
    log.info("Stage 2+3: cleaning and deduplicating...")
    cleaned = clean_items(all_raw)
    log.info(f"After cleaning: {len(cleaned)} items (was {len(all_raw)})")

    # ── Stage 4: FILTER (language tag + section + keyword) ───────────────────
    log.info("Stage 4: applying language and keyword filters...")
    filtered = apply_filters(cleaned)
    log.info(f"After filtering: {len(filtered)} items ready for extraction")

    # Update per-source counts in health summary
    for r in source_results:
        r["after_filter"] = sum(
            1 for item in filtered if item["outlet"] == r["outlet"]
        )

    print_health_summary(source_results)

    if dry_run:
        log.info("DRY RUN — not saving to database.")
        print(f"\nSample of filtered items ({min(5, len(filtered))}):")
        for item in filtered[:5]:
            print(f"  [{item['language']}] {item['outlet']}: {item['headline'][:80]}")
        return filtered

    # ── Stage 5: LLM EXTRACTION (optional) ───────────────────────────────────
    log.info("Stage 5: LLM extraction (if available)...")
    ready_to_save = _try_extract(filtered)

    # ── Stage 6: SAVE TO DATABASE ─────────────────────────────────────────────
    log.info("Saving to database...")
    saved = save_to_db(ready_to_save)
    log.info(f"Saved {saved} new items ({len(ready_to_save) - saved} duplicates skipped)")

    # ── Stage 7: VECTOR STORE SYNC (ChromaDB) ─────────────────────────────────
    try:
        from database.vector_store import sync_from_sqlite
        synced = sync_from_sqlite()
        log.info(f"Vector store synced: {synced} items in ChromaDB")
    except Exception as e:
        log.warning(f"Vector store sync skipped: {e}")

    return ready_to_save


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LankaMarket Scout — news collector (Stages 1–5)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch, clean and filter but do NOT save to the database"
    )
    parser.add_argument(
        "--lang", choices=["si", "ta", "en"],
        help="Only collect from feeds in this language"
    )
    args = parser.parse_args()
    collect_all(dry_run=args.dry_run, lang_filter=args.lang)
