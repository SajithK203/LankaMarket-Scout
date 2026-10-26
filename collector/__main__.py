"""
collector/__main__.py
---------------------
Allows running `python -m collector` as a shortcut for `python -m collector.collect`.
"""
import argparse
import io
import sys

# Force UTF-8 output on Windows (avoids cp1252 crash on arrow/emoji chars)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from collector.collect import collect_all

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
