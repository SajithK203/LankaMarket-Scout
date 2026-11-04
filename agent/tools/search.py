"""
agent/tools/search.py
---------------------
Tool 1: search_news & semantic_search_news
Queries the SQLite database and ChromaDB vector store for business-relevant
news items filtered and ranked by relevance to the user's specific venture.
"""

import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.db import get_connection, query_facts
from database.vector_store import semantic_search


def _calculate_relevance(item: dict, query: str | None, target_sectors: list[str], target_districts: list[str]) -> float:
    """
    Score relevance of a news item to the user's business query.
    Higher score = more relevant.
    """
    score = 0.0
    text = (f"{item.get('headline', '')} {item.get('summary_en', '')}").lower()
    
    # 1. Base semantic score if present from vector search
    base_vector_score = item.get("confidence", 0.0)
    if isinstance(base_vector_score, (int, float)):
        score += float(base_vector_score) * 1.5

    # 2. Query keyword overlap
    if query:
        q_words = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 3]
        for w in q_words:
            if w in text:
                score += 0.8

    # 3. Target district relevance (e.g. Kandy)
    item_districts = item.get("districts", [])
    if isinstance(item_districts, str):
        try:
            item_districts = json.loads(item_districts)
        except Exception:
            item_districts = [item_districts]
            
    for d in target_districts:
        if d.lower() != "national" and d.lower() in [x.lower() for x in item_districts]:
            score += 2.0  # Big boost for local news in target district

    # 4. Target sector relevance
    item_sectors = item.get("sectors", [])
    if isinstance(item_sectors, str):
        try:
            item_sectors = json.loads(item_sectors)
        except Exception:
            item_sectors = [item_sectors]

    common_sectors = set(s.lower() for s in target_sectors) & set(s.lower() for s in item_sectors)
    if common_sectors and "other" not in common_sectors:
        score += 1.2

    # 5. Absolute disqualification for sports, crime, celebrity, or foreign military
    strict_disqualify = [
        "cricket", "match", "tournament", "තරඟය", "තරගය", "ක්‍රිකට්", "ipl", "odi", "t20", "football",
        "israel", "sudan", "gaza", "beirut", "lebanon", "hamas", "ukraine", "russia",
        "court", "arrest", "bail", "murder", "narcotics", "හිරගෙදර", "අධිකරණ", "පොලිස්",
        "airport", "ගුවන් තොටුපළ", "විදේශ සේවා", "diploma", "award"
    ]
    if any(p in text for p in strict_disqualify):
        return -999.0  # Discard immediately from business report

    # 6. Specific boosts for core micro-business cost factors (energy/food/inflation)
    cost_keywords = ["fuel", "gas", "litro", "electricity", "ceb", "price", "cut", "inflation", "cost", "flour", "bread", "food"]
    if any(c in text for c in cost_keywords):
        score += 0.7

    return score


def search_news(
    districts: list[str],
    sectors: list[str],
    days: int = 90,
    direction: str | None = None,
    query: str | None = None,
) -> dict:
    """
    Search and rank stored news facts combining structured filtering with semantic relevance.
    Returns the most relevant items first, discarding off-topic results.
    """
    conn = get_connection()
    raw_items = query_facts(conn, districts=districts, sectors=sectors,
                            direction=direction, days=days)
    conn.close()

    items_dict: dict[str, dict] = {i["link"]: dict(i) for i in raw_items}

    # Enrich with semantic search if query is available
    if query:
        vector_hits = semantic_search(query, n_results=15)
        for hit in vector_hits:
            link = hit.get("link")
            if link and link not in items_dict:
                items_dict[link] = {
                    "id": hit.get("id"),
                    "headline": hit.get("document", "").splitlines()[0],
                    "summary_en": hit.get("document", ""),
                    "link": link,
                    "outlet": hit.get("outlet", "News"),
                    "headline_lang": hit.get("language", "en"),
                    "direction": hit.get("direction", "mixed"),
                    "confidence": hit.get("score", 0.5),
                    "sectors": sectors,
                    "districts": districts,
                    "published_at": hit.get("published_at", "recent"),
                }

    # Calculate relevance for each item and filter out off-topic items
    scored_items = []
    for item in items_dict.values():
        rel = _calculate_relevance(item, query, sectors, districts)
        item["relevance_score"] = rel
        if rel >= 0.8:  # Drop off-topic items
            scored_items.append(item)

    # Sort descending by relevance score (most relevant first!)
    scored_items.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    # Return top-K most relevant items (up to 7)
    final_items = scored_items[:7]

    return {
        "items": final_items,
        "count": len(final_items),
        "districts": districts,
        "sectors": sectors,
        "days": days,
    }


def search_news_semantic(query: str, n_results: int = 8) -> dict:
    """
    Semantic-first vector search across news items.
    """
    hits = semantic_search(query, n_results=n_results)
    return {
        "items": hits,
        "count": len(hits),
        "query": query,
    }
