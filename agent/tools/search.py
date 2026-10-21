"""
agent/tools/search.py
---------------------
Tool 1: search_news
Queries the SQLite database for business-relevant news items
filtered by district, sector, and recency.

The agent calls this tool when it needs evidence from stored news.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.db import get_connection, query_facts


def search_news(
    districts: list[str],
    sectors: list[str],
    days: int = 90,
    direction: str | None = None,
) -> dict:
    """
    Search stored news facts by district, sector and recency.

    Args:
        districts: e.g. ["Kandy", "Anuradhapura"]
        sectors:   e.g. ["food_retail", "agriculture"]
        days:      look back this many days
        direction: filter by "positive" | "negative" | "mixed" | None (all)

    Returns:
        {"items": [...], "count": N, "districts": [...], "sectors": [...]}
    """
    conn = get_connection()
    items = query_facts(conn, districts=districts, sectors=sectors,
                        direction=direction, days=days)
    conn.close()

    return {
        "items": items,
        "count": len(items),
        "districts": districts,
        "sectors": sectors,
        "days": days,
    }
