"""
agent/tools/search.py
---------------------
Tool 1: search_news & semantic_search_news
Queries the SQLite database and ChromaDB vector store for business-relevant
news items filtered by district, sector, recency, or semantic similarity.

The agent calls this tool when it needs evidence from stored news.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.db import get_connection, query_facts
from database.vector_store import semantic_search


def search_news(
    districts: list[str],
    sectors: list[str],
    days: int = 90,
    direction: str | None = None,
    query: str | None = None,
) -> dict:
    """
    Search stored news facts by district, sector, recency, and optional semantic query.

    Args:
        districts: e.g. ["Kandy", "Anuradhapura", "national"]
        sectors:   e.g. ["food_retail", "agriculture", "energy"]
        days:      look back this many days
        direction: filter by "positive" | "negative" | "mixed" | None (all)
        query:     optional natural-language semantic query

    Returns:
        {"items": [...], "count": N, "districts": [...], "sectors": [...]}
    """
    conn = get_connection()
    items = query_facts(conn, districts=districts, sectors=sectors,
                        direction=direction, days=days)
    conn.close()

    # If SQL query had few items and a semantic query string is provided, augment with vector search
    if (len(items) < 3) and query:
        vector_hits = semantic_search(query, n_results=5)
        seen_links = {i["link"] for i in items}
        for hit in vector_hits:
            if hit["link"] not in seen_links:
                items.append({
                    "id": hit["id"],
                    "headline": hit["document"].splitlines()[0],
                    "summary_en": hit["document"],
                    "link": hit["link"],
                    "outlet": hit["outlet"],
                    "headline_lang": hit["language"],
                    "direction": hit["direction"],
                    "confidence": hit["score"],
                    "sectors": sectors,
                    "districts": districts,
                })
                seen_links.add(hit["link"])

    return {
        "items": items,
        "count": len(items),
        "districts": districts,
        "sectors": sectors,
        "days": days,
    }


def search_news_semantic(query: str, n_results: int = 5) -> dict:
    """
    Semantic-first vector search across news items.
    """
    hits = semantic_search(query, n_results=n_results)
    return {
        "items": hits,
        "count": len(hits),
        "query": query,
    }
