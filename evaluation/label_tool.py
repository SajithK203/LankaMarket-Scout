"""
evaluation/label_tool.py
-------------------------
A simple command-line labelling tool for Member A and Member B.

WHAT IT DOES:
  Shows you one headline at a time from a collected CSV.
  You press keys to label it. Labels are saved automatically.
  Stop and resume anytime — it skips already-labelled items.

HOW TO RUN:
  # First collect some headlines:
  python -m collector.collect --dry-run > /dev/null  (or real collect)

  # Then export them to a CSV for labelling:
  python evaluation/label_tool.py --export data/labels/to_label.csv

  # Then label them interactively:
  python evaluation/label_tool.py --label data/labels/to_label.csv

LABEL KEYS:
  y = yes, business relevant
  n = no, not business relevant
  s = skip (unsure)
  q = quit and save

For each 'y' item, also enter:
  sector: (agriculture / food_retail / tourism / transport / other)
  district: (Kandy / Anuradhapura / Galle / national / unclear)
  direction: (positive / negative / mixed)
"""

import csv
import sys
from pathlib import Path


def label_file(csv_path: str):
    path = Path(csv_path)
    if not path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    # Load all rows
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Add label columns if not present
    for row in rows:
        for col in ["label_relevant", "label_sector", "label_district", "label_direction"]:
            if col not in row:
                row[col] = ""

    unlabelled = [r for r in rows if not r["label_relevant"]]
    print(f"\n{len(unlabelled)} items to label. Press q to quit and save.\n")

    for row in unlabelled:
        print(f"\n{'─'*60}")
        print(f"Language : {row.get('language', '?')}")
        print(f"Outlet   : {row.get('outlet', '?')}")
        print(f"Headline : {row.get('headline', '?')}")
        print(f"{'─'*60}")
        print("Is this business-relevant? (y=yes / n=no / s=skip / q=quit)")

        key = input("> ").strip().lower()
        if key == "q":
            break
        elif key == "y":
            row["label_relevant"] = "yes"
            row["label_sector"] = input("Sector (agriculture/food_retail/tourism/transport/other): ").strip()
            row["label_district"] = input("District (Kandy/Anuradhapura/Galle/national/unclear): ").strip()
            row["label_direction"] = input("Direction (positive/negative/mixed): ").strip()
        elif key == "n":
            row["label_relevant"] = "no"
        elif key == "s":
            row["label_relevant"] = "skip"

    # Save
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    labelled = sum(1 for r in rows if r["label_relevant"] in ("yes", "no"))
    print(f"\nSaved. {labelled}/{len(rows)} items labelled.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", metavar="CSV", help="CSV file to label interactively")
    args = parser.parse_args()

    if args.label:
        label_file(args.label)
    else:
        print("Usage: python evaluation/label_tool.py --label data/labels/to_label.csv")
