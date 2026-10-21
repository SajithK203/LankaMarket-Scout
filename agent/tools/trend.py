"""
agent/tools/trend.py
--------------------
Tool 2: compute_trend
Counts positive vs negative news items over time to show
whether sentiment is improving or worsening for a sector+district.

The agent uses this to give a direction signal in the report.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.db import get_connection, query_facts


def compute_trend(
    districts: list[str],
    sectors: list[str],
    days: int = 90,
) -> dict:
    """
    Count positive vs negative items in recent news.

    Returns:
        {
          "positive_count": N,
          "negative_count": N,
          "mixed_count": N,
          "trend": "improving" | "worsening" | "mixed" | "insufficient_data",
          "confidence": 0.0–1.0
        }
    """
    conn = get_connection()
    all_items = query_facts(conn, districts=districts, sectors=sectors, days=days)
    conn.close()

    pos = sum(1 for i in all_items if i["direction"] == "positive")
    neg = sum(1 for i in all_items if i["direction"] == "negative")
    mix = sum(1 for i in all_items if i["direction"] == "mixed")
    total = pos + neg + mix

    if total < 3:
        trend = "insufficient_data"
        confidence = 0.2
    elif pos > neg * 1.5:
        trend = "improving"
        confidence = min(0.5 + (total / 20), 0.9)
    elif neg > pos * 1.5:
        trend = "worsening"
        confidence = min(0.5 + (total / 20), 0.9)
    else:
        trend = "mixed"
        confidence = 0.5

    return {
        "positive_count": pos,
        "negative_count": neg,
        "mixed_count": mix,
        "total_items": total,
        "trend": trend,
        "confidence": round(confidence, 2),
    }
