"""
database/db.py
--------------
Database helpers: set up the SQLite table of structured news facts,
and provide save/query functions used by the collector and agent.

Schema design:
  - One row per news item after LLM extraction (Stage 5)
  - Structured fields allow fast SQL queries like:
      "all negative input-cost items for agriculture in Kandy in last 60 days"
  - Original headline and link kept so every agent answer can cite the source
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/lankamarket.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """
    Create the news_facts table if it does not exist yet.
    Call this once at startup.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS news_facts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            -- Original item fields
            headline        TEXT NOT NULL,
            headline_lang   TEXT NOT NULL,  -- 'si' | 'ta' | 'en'
            outlet          TEXT NOT NULL,
            link            TEXT NOT NULL UNIQUE,
            published_at    TEXT,
            collected_at    TEXT NOT NULL,
            -- LLM-extracted fields (Stage 5)
            business_relevant INTEGER DEFAULT 0,  -- 0 | 1
            impact_type     TEXT,   -- e.g. 'input_cost', 'demand', 'regulation'
            sectors         TEXT,   -- JSON array, e.g. '["agriculture","food_retail"]'
            districts       TEXT,   -- JSON array, e.g. '["Kandy","Anuradhapura"]'
            direction       TEXT,   -- 'positive' | 'negative' | 'mixed'
            confidence      REAL,   -- 0.0 – 1.0
            summary_en      TEXT,   -- one-sentence English summary
            reason          TEXT,   -- why this matters for business
            -- Embedding stored separately in ChromaDB (keyed by this id)
            embedding_id    TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_districts  ON news_facts(districts);
        CREATE INDEX IF NOT EXISTS idx_sectors    ON news_facts(sectors);
        CREATE INDEX IF NOT EXISTS idx_direction  ON news_facts(direction);
        CREATE INDEX IF NOT EXISTS idx_collected  ON news_facts(collected_at);
    """)
    conn.commit()


def save_item(conn: sqlite3.Connection, item: dict) -> int | None:
    """
    Insert one processed news item.
    Returns the new row ID, or None if the link already exists (duplicate).
    """
    try:
        cursor = conn.execute("""
            INSERT INTO news_facts (
                headline, headline_lang, outlet, link,
                published_at, collected_at,
                business_relevant, impact_type,
                sectors, districts, direction,
                confidence, summary_en, reason
            ) VALUES (
                :headline, :headline_lang, :outlet, :link,
                :published_at, :collected_at,
                :business_relevant, :impact_type,
                :sectors, :districts, :direction,
                :confidence, :summary_en, :reason
            )
        """, {
            **item,
            "sectors": json.dumps(item.get("sectors", [])),
            "districts": json.dumps(item.get("districts", [])),
            "collected_at": datetime.utcnow().isoformat(),
        })
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None  # duplicate link — skip silently


def query_facts(
    conn: sqlite3.Connection,
    districts: list[str] | None = None,
    sectors: list[str] | None = None,
    direction: str | None = None,
    days: int = 90,
) -> list[dict]:
    """
    Search news_facts by district, sector, direction and recency.
    Returns list of dicts with all fields.

    Example:
        query_facts(conn, districts=["Kandy"], sectors=["food_retail"], days=60)
    """
    # Build WHERE clause dynamically
    conditions = ["business_relevant = 1"]
    params: list = []

    if districts:
        # JSON contains check — works because districts is stored as JSON array string
        district_conditions = " OR ".join(
            ["districts LIKE ?"] * len(districts)
        )
        conditions.append(f"({district_conditions})")
        params.extend([f'%"{d}"%' for d in districts])

    if sectors:
        sector_conditions = " OR ".join(
            ["sectors LIKE ?"] * len(sectors)
        )
        conditions.append(f"({sector_conditions})")
        params.extend([f'%"{s}"%' for s in sectors])

    if direction:
        conditions.append("direction = ?")
        params.append(direction)

    conditions.append(
        f"collected_at >= datetime('now', '-{int(days)} days')"
    )

    where = " AND ".join(conditions)
    sql = f"SELECT * FROM news_facts WHERE {where} ORDER BY collected_at DESC"

    rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["sectors"] = json.loads(d["sectors"] or "[]")
        d["districts"] = json.loads(d["districts"] or "[]")
        result.append(d)
    return result


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    conn = get_connection()
    create_tables(conn)
    print("Database tables created successfully.")
    print(f"Database location: {DB_PATH.resolve()}")
