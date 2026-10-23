"""
evaluation/evaluate.py
----------------------
Precision, Recall, F1, and Attribute Evaluation Tool.

Evaluates the Stage 5 LLM / Heuristic Extractor against ground-truth human
labelled headlines created with evaluation/label_tool.py.

Metrics calculated:
  - Binary Relevance: Precision, Recall, F1-Score, Specificity, Accuracy
  - Confusion Matrix: TP, FP, TN, FN counts
  - Sector & District Match Rate on business-relevant items
  - Direction / Sentiment Agreement

Usage:
  python -m evaluation.evaluate --file data/labels/sinhala_labels.csv
  python -m evaluation.evaluate --file data/labels/tamil_labels.csv
  python -m evaluation.evaluate --all
"""

import argparse
import csv
import sys
from pathlib import Path
from tabulate import tabulate

from collector.extractor import extract_item


def evaluate_file(csv_path: str | Path) -> dict:
    """Evaluate extractor predictions on a single CSV file."""
    path = Path(csv_path)
    if not path.exists():
        print(f"Error: File not found: {path}")
        return {}

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # Keep only rows that have a ground-truth label
    labelled = [
        r for r in rows
        if r.get("label_relevant") in ("yes", "no", "y", "n")
    ]

    if not labelled:
        print(f"No labelled rows found in {path.name}.")
        return {}

    tp = fp = tn = fn = 0
    sector_matches = 0
    district_matches = 0
    direction_matches = 0
    relevant_count = 0

    detailed_results = []

    for row in labelled:
        gt_yes = row["label_relevant"] in ("yes", "y")
        gt_relevant = 1 if gt_yes else 0

        # Predict using extractor
        item = {
            "headline": row["headline"],
            "language": row.get("language") or ("si" if "sinhala" in path.name else "ta"),
            "outlet": row.get("outlet", ""),
            "link": row.get("link", ""),
        }
        pred = extract_item(item)
        pred_relevant = pred.get("business_relevant", 0)

        # Binary confusion matrix
        if gt_relevant == 1 and pred_relevant == 1:
            tp += 1
        elif gt_relevant == 0 and pred_relevant == 1:
            fp += 1
        elif gt_relevant == 0 and pred_relevant == 0:
            tn += 1
        elif gt_relevant == 1 and pred_relevant == 0:
            fn += 1

        # Evaluate attributes on relevant items
        if gt_relevant == 1:
            relevant_count += 1
            gt_sector = (row.get("label_sector") or "").strip().lower()
            pred_sectors = [s.lower() for s in pred.get("sectors", [])]
            if gt_sector and (gt_sector in pred_sectors or any(gt_sector in s for s in pred_sectors)):
                sector_matches += 1

            gt_district = (row.get("label_district") or "").strip().lower()
            pred_districts = [d.lower() for d in pred.get("districts", [])]
            if gt_district and (gt_district in pred_districts or (gt_district == "national" and "national" in pred_districts)):
                district_matches += 1

            gt_direction = (row.get("label_direction") or "").strip().lower()
            pred_direction = (pred.get("direction") or "").strip().lower()
            if gt_direction and gt_direction == pred_direction:
                direction_matches += 1

        detailed_results.append({
            "headline": row["headline"][:45] + "...",
            "GT": "YES" if gt_relevant else "NO",
            "Pred": "YES" if pred_relevant else "NO",
            "Sectors": ", ".join(pred.get("sectors", [])),
            "Districts": ", ".join(pred.get("districts", [])),
            "Dir": pred.get("direction", ""),
        })

    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0

    return {
        "file": path.name,
        "total": total,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": specificity,
        "relevant_count": relevant_count,
        "sector_acc": (sector_matches / relevant_count) if relevant_count > 0 else 0.0,
        "district_acc": (district_matches / relevant_count) if relevant_count > 0 else 0.0,
        "direction_acc": (direction_matches / relevant_count) if relevant_count > 0 else 0.0,
        "details": detailed_results,
    }


def print_evaluation_report(results: list[dict]) -> None:
    """Print standard benchmark tables for judges."""
    print("\n" + "=" * 76)
    print("           LANKAMARKET SCOUT — EXTRACTOR EVALUATION REPORT           ")
    print("=" * 76)

    table_data = []
    for r in results:
        table_data.append([
            r["file"],
            r["total"],
            f"{r['precision'] * 100:.1f}%",
            f"{r['recall'] * 100:.1f}%",
            f"{r['f1'] * 100:.1f}%",
            f"{r['accuracy'] * 100:.1f}%",
            f"TP:{r['tp']} FP:{r['fp']} TN:{r['tn']} FN:{r['fn']}",
            f"{r['sector_acc'] * 100:.0f}%",
            f"{r['district_acc'] * 100:.0f}%",
        ])

    headers = [
        "Dataset", "Sample", "Precision", "Recall", "F1 Score",
        "Accuracy", "Confusion Matrix", "Sector Acc", "District Acc"
    ]
    print(tabulate(table_data, headers=headers, tablefmt="github"))
    print("=" * 76)

    # Detailed predictions breakdown
    for r in results:
        print(f"\n--- Item Breakdown: {r['file']} ---")
        detail_table = [
            [d["headline"], d["GT"], d["Pred"], d["Sectors"], d["Districts"], d["Dir"]]
            for d in r["details"]
        ]
        print(tabulate(detail_table, headers=["Headline", "GT", "Pred", "Sectors", "Districts", "Direction"], tablefmt="simple"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Stage 5 Extractor on Hand-labelled Datasets")
    parser.add_argument("--file", help="Path to labelled CSV file")
    parser.add_argument("--all", action="store_true", help="Evaluate all CSVs in data/labels/")
    args = parser.parse_args()

    files_to_eval = []
    if args.file:
        files_to_eval.append(Path(args.file))
    elif args.all or len(sys.argv) == 1:
        labels_dir = Path("data/labels")
        if labels_dir.exists():
            files_to_eval = sorted(list(labels_dir.glob("*_labels.csv")))

    if not files_to_eval:
        print("No label files specified or found.")
        sys.exit(1)

    all_results = []
    for f in files_to_eval:
        res = evaluate_file(f)
        if res:
            all_results.append(res)

    if all_results:
        print_evaluation_report(all_results)


if __name__ == "__main__":
    main()
