"""
collector/collect.py
--------------------
Stage 1 of the pipeline: fetch RSS feeds listed in sources.yaml,
clean each item, deduplicate, and save to the database.

Run:
    python -m collector.collect --dry-run    # fetch but do not save
    python -m collector.collect              # fetch and save to DB
"""

import argparse
import logging
import time
from pathlib import Path

import feedparser
import requests
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SOURCES_PATH = Path("data/feeds/sources.yaml")
REQUEST_DELAY = 3   # seconds between requests to the same site (polite!)
USER_AGENT = "LankaMarketScout/0.1 (research prototype)"


def load_sources(path: Path) -> list[dict]:
    """Load feed list from sources.yaml, skip entries without a URL."""
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = [s for s in config["sources"] if s.get("url")]
    log.info(f"Loaded {len(sources)} sources with URLs from {path}")
    return sources


def check_robots(base_url: str) -> bool:
    """
    IMPORTANT: Always check robots.txt before fetching.
    Returns True if fetching RSS is allowed (or if robots.txt is unreachable).
    This is a simplified check — in production, use the `robotparser` stdlib module.
    """
    try:
        robots_url = base_url.rstrip("/") + "/robots.txt"
        resp = requests.get(robots_url, timeout=5, headers={"User-Agent": USER_AGENT})
        if resp.status_code == 200 and "Disallow: /" in resp.text:
            log.warning(f"robots.txt may disallow crawling: {robots_url}")
            return False
    except Exception:
        pass  # If robots.txt is unreachable, proceed but log it
    return True


def fetch_feed(source: dict) -> list[dict]:
    """
    Fetch one RSS feed and return a list of raw items.
    Each item: {headline, link, published, outlet, language, section}
    """
    url = source["url"]
    outlet = source["name"]
    language = source["language"]
    section = source.get("section", "general")

    # Polite headers — never disguise the bot
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "si, ta, en"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception as e:
        log.error(f"Failed to fetch {outlet} ({url}): {e}")
        return []

    items = []
    for entry in feed.entries:
        headline = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        published = entry.get("published", entry.get("updated", ""))

        if not headline or not link:
            continue

        items.append({
            "headline": headline,
            "link": link,
            "published": published,
            "outlet": outlet,
            "language": language,
            "section": section,
        })

    log.info(f"  {outlet}: {len(items)} items fetched")
    return items


def collect_all(dry_run: bool = False) -> list[dict]:
    """
    Main collection function.
    Fetches all sources, cleans, and (unless dry_run) saves to DB.
    """
    sources = load_sources(SOURCES_PATH)
    all_items = []

    for source in sources:
        if source.get("status") == "skip":
            continue

        # Check robots.txt (simplified)
        from urllib.parse import urlparse
        base = f"{urlparse(source['url']).scheme}://{urlparse(source['url']).netloc}"
        if not check_robots(base):
            log.warning(f"Skipping {source['name']} — robots.txt check failed")
            continue

        items = fetch_feed(source)
        all_items.extend(items)

        # Polite pause between requests
        time.sleep(REQUEST_DELAY)

    log.info(f"Total items fetched: {len(all_items)}")

    if dry_run:
        log.info("DRY RUN — not saving to database")
        for item in all_items[:5]:
            print(f"  [{item['language']}] {item['outlet']}: {item['headline'][:80]}")
    else:
        # TODO (Member A): wire up to database/db.py save function
        log.info("Saving to database... (not yet implemented — see database/db.py)")

    return all_items


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LankaMarket Scout — news collector")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but do not save")
    args = parser.parse_args()
    collect_all(dry_run=args.dry_run)
