"""
scripts/check_feeds.py
----------------------
Member A's first tool: test which RSS feeds actually work from our network.

Run:
    python scripts/check_feeds.py
    python scripts/check_feeds.py --lang si    # only Sinhala feeds
    python scripts/check_feeds.py --lang ta    # only Tamil feeds

Output: a table showing which feeds work, how many items they returned,
and any errors. Copy the results into data/feeds/sources.yaml (update the
'status' field).
"""

import sys
import time
import argparse
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
import yaml
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).parent.parent))

SOURCES_PATH = Path("data/feeds/sources.yaml")
USER_AGENT = "LankaMarketScout/0.1 (research prototype - feed test)"
REQUEST_DELAY = 3  # seconds between requests


def check_one_feed(source: dict) -> dict:
    """Test a single feed and return a result dict."""
    url = source["url"]
    if not url:
        return {
            "name": source["name"],
            "language": source["language"],
            "url": "(no URL)",
            "status": "NO URL",
            "item_count": 0,
            "sample": "",
            "error": "URL not set in sources.yaml",
        }

    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        status_code = resp.status_code

        if status_code != 200:
            return {
                "name": source["name"],
                "language": source["language"],
                "url": url,
                "status": f"HTTP {status_code}",
                "item_count": 0,
                "sample": "",
                "error": f"HTTP error {status_code}",
            }

        feed = feedparser.parse(resp.content)
        items = feed.entries
        sample = items[0].get("title", "")[:70] if items else ""

        return {
            "name": source["name"],
            "language": source["language"],
            "url": url,
            "status": "✅ OK",
            "item_count": len(items),
            "sample": sample,
            "error": "",
        }

    except requests.exceptions.Timeout:
        return {
            "name": source["name"],
            "language": source["language"],
            "url": url,
            "status": "❌ TIMEOUT",
            "item_count": 0,
            "sample": "",
            "error": "Request timed out after 10 seconds",
        }
    except Exception as e:
        return {
            "name": source["name"],
            "language": source["language"],
            "url": url,
            "status": "❌ ERROR",
            "item_count": 0,
            "sample": "",
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Test RSS feeds from sources.yaml")
    parser.add_argument("--lang", choices=["si", "ta", "en"], help="Filter by language")
    args = parser.parse_args()

    with open(SOURCES_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = config["sources"]

    if args.lang:
        sources = [s for s in sources if s["language"] == args.lang]

    print(f"\nTesting {len(sources)} feeds... (polite {REQUEST_DELAY}s delay between requests)\n")

    results = []
    for i, source in enumerate(sources):
        print(f"  [{i+1}/{len(sources)}] Testing: {source['name']}...")
        result = check_one_feed(source)
        results.append(result)
        time.sleep(REQUEST_DELAY)

    # Print summary table
    print("\n" + "="*80)
    print("FEED TEST RESULTS")
    print("="*80)
    table = [
        [r["name"], r["language"], r["status"], r["item_count"], r["sample"][:50]]
        for r in results
    ]
    print(tabulate(table, headers=["Outlet", "Lang", "Status", "Items", "Sample headline"]))

    # Print errors separately
    errors = [r for r in results if r["error"]]
    if errors:
        print("\n" + "="*80)
        print("ERRORS / FAILURES")
        print("="*80)
        for r in errors:
            print(f"  {r['name']}: {r['error']}")

    # Summary counts
    ok = sum(1 for r in results if "OK" in r["status"])
    print(f"\nSummary: {ok}/{len(results)} feeds working")
    print("\nNext step: update 'status' field in data/feeds/sources.yaml based on these results.")


if __name__ == "__main__":
    main()
