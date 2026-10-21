# status.md — Feature Status Report
# Update this table every time something changes.
# Honest reporting is rewarded by judges. NEVER hide a mocked feature.

| Feature | Status | Notes |
|---|---|---|
| RSS feed collection | 🔄 In Progress | `scripts/check_feeds.py` written; feeds not yet tested from our network |
| Text cleaning (HTML, Unicode NFC) | ✅ Done | `collector/cleaner.py` |
| Legacy Sinhala font detection | ✅ Done | `collector/cleaner.py` — detects and skips |
| Deduplication | ✅ Done | `collector/cleaner.py` — by link and headline similarity |
| Language detection | ❌ Not started | `langdetect` / `fasttext` to be wired in |
| Keyword filter (Stage 4) | ❌ Not started | `data/keywords/` files to be created |
| LLM extraction (Stage 5) | ❌ Not started | Prompt drafted in Appendix B of project guide |
| SQLite database schema | ✅ Done | `database/db.py` — schema and query helpers |
| Vector store (ChromaDB) | ❌ Not started | For semantic / cross-lingual search |
| Agent loop | 🟡 Mocked | `agent/loop.py` — structure complete; LLM calls are mocked |
| search_news tool | 🟡 Mocked | `agent/tools/search.py` — queries DB; DB is empty until collector runs |
| compute_trend tool | 🟡 Mocked | `agent/tools/trend.py` — logic done; depends on real data |
| write_report tool | ✅ Done | `agent/tools/report.py` — full structure; generates from evidence |
| Streamlit interface | ❌ Not started | `interface/app.py` to be built |
| Evaluation (precision/recall) | ❌ Not started | Need 100 labelled headlines first |
| User interviews | ❌ Not started | Target: 3-5 business owners before proposal submission |

## Feed Status

| Outlet | Language | Status | Notes |
|---|---|---|---|
| Lankadeepa | si | 🔄 Unverified | Test from our network |
| Ada Derana Sinhala | si | ⛔ Blocked (cloud) | Test from home network |
| Virakesari | ta | ❓ No URL | Find RSS URL first |
| EconomyNext | en | 🔄 Unverified | Test |
| Daily FT | en | 🔄 Unverified | Test |

## Cost Tracking

| Item | Estimate | Actual (fill in after testing) |
|---|---|---|
| LLM calls per 1,000 headlines | TBD | — |
| LLM calls per agent question | TBD | — |
| Embedding cost per 1,000 items | $0 (local model) | — |
