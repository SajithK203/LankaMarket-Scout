"""
evaluation/label_tool.py
-------------------------
A simple command-line labelling tool for Member A (Sinhala) and Member B (Tamil).

WHY WE NEED THIS:
  Judges ask for precision and recall numbers.  To compute them, we need a
  set of headlines where we, as humans, know the right answer.  Then we
  compare: did the LLM agree with us?

WORKFLOW:
  Step 1 — Export headlines from the database into a CSV for labelling:
      python evaluation/label_tool.py --export data/labels/sinhala_labels.csv --lang si --limit 50

  Step 2 — Label them interactively one at a time:
      python evaluation/label_tool.py --label data/labels/sinhala_labels.csv

  Step 3 — Check progress at any time:
      python evaluation/label_tool.py --stats data/labels/sinhala_labels.csv

  You can stop and resume labelling anytime — already-labelled items are skipped.

LABEL KEYS (during --label mode):
  y = yes, this headline is business-relevant
  n = no, not business-relevant
  s = skip / unsure (label left blank, can return to it later)
  q = quit and save progress

For each 'y' item you also enter:
  sector   : agriculture / food_retail / tourism / transport / construction / services / other
  district : Kandy / Anuradhapura / Galle / national / unclear
  direction: positive / negative / mixed

Member A owns Sinhala labels. Member B owns Tamil labels.
"""

import csv
import sqlite3
import sys
from pathlib import Path


# ── Export from database ──────────────────────────────────────────────────────

def export_from_db(csv_path: str, lang: str = "si", limit: int = 50) -> None:
    """
    Pull unlabelled headlines from the SQLite database into a CSV file.
    Creates the file if it does not exist. Skips headlines already in the file.

    Args:
        csv_path : path to the output CSV (e.g. data/labels/sinhala_labels.csv)
        lang     : 'si' | 'ta' | 'en'
        limit    : maximum number of rows to export
    """
    db_path = Path("data/lankamarket.db")
    if not db_path.exists():
        print(
            f"Database not found at {db_path}.\n"
            "Run the collector first:\n"
            "  python -m collector.collect\n"
            "Or do a dry-run to see headlines without saving:\n"
            "  python -m collector.collect --dry-run"
        )
        sys.exit(1)

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Load already-exported links so we don't duplicate
    existing_links: set[str] = set()
    if out_path.exists():
        with open(out_path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            existing_links = {row.get("link", "") for row in reader}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT headline, link, outlet, headline_lang AS language, published_at "
        "FROM news_facts "
        "WHERE headline_lang = ? "
        "ORDER BY collected_at DESC "
        "LIMIT ?",
        (lang, limit * 3),  # fetch extra because we skip duplicates
    ).fetchall()
    conn.close()

    new_rows = [dict(r) for r in rows if r["link"] not in existing_links][:limit]

    if not new_rows:
        print(f"No new {lang} headlines found in database. Run the collector to get more data.")
        return

    # Add empty label columns
    for row in new_rows:
        row.update({
            "label_relevant":  "",
            "label_sector":    "",
            "label_district":  "",
            "label_direction": "",
        })

    # Append or create
    fieldnames = ["headline", "link", "outlet", "language", "published_at",
                  "label_relevant", "label_sector", "label_district", "label_direction"]

    file_exists = out_path.exists() and out_path.stat().st_size > 0
    with open(out_path, "a" if file_exists else "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)

    print(f"Exported {len(new_rows)} new {lang.upper()} headlines to {out_path}")
    print(f"Next: python evaluation/label_tool.py --label {csv_path}")


# ── Interactive labelling ─────────────────────────────────────────────────────

_VALID_SECTORS   = ("agriculture", "food_retail", "tourism", "transport",
                    "construction", "services", "other")
_VALID_DISTRICTS = ("Kandy", "Anuradhapura", "Galle", "national", "unclear")
_VALID_DIRECTIONS = ("positive", "negative", "mixed")


def _prompt_choice(prompt: str, valid: tuple[str, ...]) -> str:
    """Prompt the user until they enter one of the valid options."""
    options = " / ".join(valid)
    while True:
        val = input(f"{prompt} ({options}): ").strip().lower()
        # Accept prefix matching (e.g. 'ag' → 'agriculture')
        matches = [v for v in valid if v.lower().startswith(val)]
        if len(matches) == 1:
            return matches[0]
        if val in valid:
            return val
        print(f"  Please enter one of: {options}")


def label_file(csv_path: str) -> None:
    """
    Show each unlabelled headline one at a time and ask for human labels.
    Progress is saved after every item so you can quit (q) at any time.
    """
    path = Path(csv_path)
    if not path.exists():
        print(
            f"File not found: {csv_path}\n"
            "Export headlines first:\n"
            "  python evaluation/label_tool.py --export <path> --lang si"
        )
        sys.exit(1)

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Add label columns if an old export is missing them
    for row in rows:
        for col in ("label_relevant", "label_sector", "label_district", "label_direction"):
            if col not in row:
                row[col] = ""

    fieldnames = list(rows[0].keys())

    unlabelled = [r for r in rows if not r["label_relevant"]]
    total = len(rows)
    labelled_before = total - len(unlabelled)

    print(f"\n{'─'*60}")
    print(f"  LankaMarket Scout — headline labelling tool")
    print(f"  File     : {path.name}")
    print(f"  Progress : {labelled_before}/{total} labelled, {len(unlabelled)} remaining")
    print(f"  Keys     : y=relevant  n=not relevant  s=skip  q=quit & save")
    print(f"{'─'*60}\n")

    for idx, row in enumerate(unlabelled):
        position = labelled_before + idx + 1
        print(f"\n[{position}/{total}]  Lang: {row.get('language','?')}  |  Outlet: {row.get('outlet','?')}")
        print(f"Headline: {row.get('headline','?')}")
        print("─" * 60)

        key = input("Business-relevant? (y / n / s=skip / q=quit): ").strip().lower()

        if key == "q":
            print("\nQuitting — saving progress...")
            break
        elif key == "y":
            row["label_relevant"] = "yes"
            row["label_sector"]    = _prompt_choice("  Sector", _VALID_SECTORS)
            row["label_district"]  = _prompt_choice("  District", _VALID_DISTRICTS)
            row["label_direction"] = _prompt_choice("  Direction", _VALID_DIRECTIONS)
        elif key == "n":
            row["label_relevant"] = "no"
        else:
            row["label_relevant"] = "skip"

        # Save after every item so progress is never lost
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    labelled_after = sum(1 for r in rows if r["label_relevant"] in ("yes", "no"))
    print(f"\nSaved. {labelled_after}/{total} items labelled "
          f"({sum(1 for r in rows if r['label_relevant'] == 'yes')} relevant, "
          f"{sum(1 for r in rows if r['label_relevant'] == 'no')} not relevant).")
    print("Run --stats to see a summary.")


# ── Stats report ──────────────────────────────────────────────────────────────

def print_stats(csv_path: str) -> None:
    """Print a summary of labelling progress for a CSV file."""
    path = Path(csv_path)
    if not path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    total    = len(rows)
    yes      = sum(1 for r in rows if r.get("label_relevant") == "yes")
    no       = sum(1 for r in rows if r.get("label_relevant") == "no")
    skipped  = sum(1 for r in rows if r.get("label_relevant") == "skip")
    unlabelled = total - yes - no - skipped

    print(f"\n{'─'*50}")
    print(f"  Label stats: {path.name}")
    print(f"{'─'*50}")
    print(f"  Total rows   : {total}")
    print(f"  Labelled     : {yes + no}  ({int((yes+no)/total*100) if total else 0}%)")
    print(f"    → relevant   : {yes}")
    print(f"    → irrelevant : {no}")
    print(f"  Skipped      : {skipped}")
    print(f"  Unlabelled   : {unlabelled}")
    print(f"{'─'*50}\n")

    if yes + no >= 30:
        print("✅ Enough labelled rows for a meaningful precision/recall report.")
    elif yes + no > 0:
        print(f"⚠️  Label {30 - (yes+no)} more rows to reach the minimum (30) for evaluation.")
    else:
        print("❌ No labels yet. Run --label to start labelling.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="LankaMarket Scout — headline labelling tool"
    )
    parser.add_argument(
        "--export", metavar="CSV",
        help="Export unlabelled headlines from the DB into a CSV file"
    )
    parser.add_argument(
        "--label", metavar="CSV",
        help="Label headlines in an existing CSV file interactively"
    )
    parser.add_argument(
        "--stats", metavar="CSV",
        help="Show labelling progress for a CSV file"
    )
    parser.add_argument(
        "--lang", choices=["si", "ta", "en"], default="si",
        help="Language filter for --export (default: si)"
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Max headlines to export (default: 50)"
    )
    args = parser.parse_args()

    if args.export:
        export_from_db(args.export, lang=args.lang, limit=args.limit)
    elif args.label:
        label_file(args.label)
    elif args.stats:
        print_stats(args.stats)
    else:
        parser.print_help()
