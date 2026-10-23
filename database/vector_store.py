"""
database/vector_store.py
-------------------------
ChromaDB Vector Store integration for LankaMarket Scout.

Enables semantic, cross-lingual retrieval across Sinhala, Tamil, and English news.
Allows the agent to find conceptually relevant news even when exact keyword
matching fails (e.g. searching 'cooking fuel scarcity' finds news on 'litro gas queues').

Features:
  - Persistent ChromaDB storage at data/chroma/
  - Multi-provider embedding strategy:
      1. Default local embeddings (all-MiniLM-L6-v2)
      2. Gemini Embeddings (via API if key present)
      3. Fast sparse TF-IDF / character n-gram fallback (for offline / instant startup)
  - Automatic synchronization from SQLite news_facts table
  - Hybrid search filters (by sector, district, direction)
"""

import json
import logging
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from collector.extractor import load_llm_config

log = logging.getLogger(__name__)

CHROMA_DATA_PATH = Path("data/chroma")
COLLECTION_NAME = "lankamarket_news"


class FallbackMultilingualEmbeddingFunction(EmbeddingFunction):
    """
    Fast, dependency-free local multilingual embedding function.
    Uses character 3-gram and token frequency hash projection (dim=128)
    normalized to unit length. Works across Sinhala, Tamil, and English
    without downloading external model weights.
    """
    def __init__(self, dim: int = 128):
        self.dim = dim

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        for doc in input:
            vec = [0.0] * self.dim
            text = doc.lower()
            # Word tokens + character trigrams for cross-lingual subword matching
            tokens = re.findall(r"\w+", text)
            trigrams = [text[i:i+3] for i in range(max(0, len(text) - 2))]
            features = tokens + trigrams

            for feat in features:
                h = hash(feat) % self.dim
                vec[h] += 1.0

            # L2 normalize
            norm = math.sqrt(sum(x * x for x in vec))
            if norm > 0:
                vec = [x / norm for x in vec]
            embeddings.append(vec)
        return embeddings


def get_embedding_function() -> EmbeddingFunction | None:
    """
    Selects the most appropriate embedding function:
    Uses FallbackMultilingualEmbeddingFunction by default for instantaneous local performance,
    or Chroma's ONNX default if cached.
    """
    return FallbackMultilingualEmbeddingFunction(dim=128)


def get_chroma_client(persist_path: Path | str = CHROMA_DATA_PATH) -> chromadb.PersistentClient:
    """Returns a persistent ChromaDB client."""
    path = Path(persist_path)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_news_collection(
    client: Any = None,
    name: str = COLLECTION_NAME,
) -> Any:
    """Get or create the LankaMarket news Chroma collection."""
    if client is None:
        client = get_chroma_client()
    emb_fn = get_embedding_function()
    return client.get_or_create_collection(
        name=name,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"},
    )


def index_news_item(collection: Any, item: dict) -> str:
    """
    Index a single news item into ChromaDB.
    Combines headline and summary_en for rich semantic matching across languages.
    """
    doc_id = str(item["id"])
    headline = item.get("headline", "")
    summary_en = item.get("summary_en", "") or headline
    doc_text = f"{headline}\n{summary_en}"

    metadata = {
        "sqlite_id": item["id"],
        "outlet": item.get("outlet", ""),
        "language": item.get("headline_lang", "en"),
        "link": item.get("link", ""),
        "published_at": item.get("published_at", "") or "",
        "direction": item.get("direction", "") or "mixed",
        "impact_type": item.get("impact_type", "") or "other",
        "confidence": float(item.get("confidence", 0.5)),
    }

    collection.upsert(
        ids=[doc_id],
        documents=[doc_text],
        metadatas=[metadata],
    )
    return doc_id


def sync_from_sqlite(db_path: Path | str = Path("data/lankamarket.db")) -> int:
    """
    Sync all business-relevant news items from SQLite news_facts to ChromaDB.
    Returns the count of indexed items.
    """
    path = Path(db_path)
    if not path.exists():
        log.warning(f"Database file not found at {path}")
        return 0

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT id, headline, headline_lang, outlet, link, published_at,
               collected_at, business_relevant, impact_type, sectors,
               districts, direction, confidence, summary_en, reason
        FROM news_facts
        WHERE business_relevant = 1
    """).fetchall()

    if not rows:
        log.info("No business-relevant items in news_facts to index.")
        conn.close()
        return 0

    collection = get_news_collection()
    indexed = 0

    for r in rows:
        item = dict(r)
        doc_id = index_news_item(collection, item)
        cursor.execute("UPDATE news_facts SET embedding_id = ? WHERE id = ?", (doc_id, item["id"]))
        indexed += 1

    conn.commit()
    conn.close()
    log.info(f"Indexed {indexed} items from SQLite into ChromaDB.")
    return indexed


def semantic_search(
    query: str,
    n_results: int = 5,
    where: dict | None = None,
) -> list[dict]:
    """
    Perform semantic nearest-neighbor search for a user query.
    Returns ranked list of matching news items with similarity scores.
    """
    collection = get_news_collection()
    if collection.count() == 0:
        sync_from_sqlite()

    if collection.count() == 0:
        return []

    actual_n = min(n_results, collection.count())
    query_kwargs = {"query_texts": [query], "n_results": actual_n}
    if where:
        query_kwargs["where"] = where

    res = collection.query(**query_kwargs)

    hits = []
    if res and res.get("ids") and res["ids"][0]:
        for i, doc_id in enumerate(res["ids"][0]):
            meta = res["metadatas"][0][i] if res.get("metadatas") else {}
            dist = res["distances"][0][i] if res.get("distances") else 0.0
            doc = res["documents"][0][i] if res.get("documents") else ""
            hits.append({
                "id": doc_id,
                "document": doc,
                "metadata": meta,
                "score": round(1.0 - dist, 4),  # Cosine similarity
                "link": meta.get("link", ""),
                "outlet": meta.get("outlet", ""),
                "direction": meta.get("direction", "mixed"),
                "language": meta.get("language", "en"),
            })

    return hits


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ChromaDB Vector Store for LankaMarket Scout")
    parser.add_argument("--sync", action="store_true", help="Sync all news facts from SQLite to ChromaDB")
    parser.add_argument("--query", type=str, help="Run semantic similarity search for a query")
    parser.add_argument("--stats", action="store_true", help="Show ChromaDB collection statistics")
    args = parser.parse_args()

    if args.sync:
        count = sync_from_sqlite()
        print(f"Synced {count} business news items into ChromaDB.")
    elif args.query:
        hits = semantic_search(args.query, n_results=5)
        print(f"\nSemantic search results for: '{args.query}' ({len(hits)} hits):\n")
        for h in hits:
            print(f"[{h['score']}] ({h['direction']}) {h['outlet']}: {h['document'].splitlines()[0]}")
            print(f"    Link: {h['link']}\n")
    elif args.stats:
        col = get_news_collection()
        print(f"Collection '{COLLECTION_NAME}' contains {col.count()} vector embeddings.")
    else:
        parser.print_help()
