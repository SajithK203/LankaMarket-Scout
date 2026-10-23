# status.md — Feature Status Report
# Update this table every time something changes.
# Honest reporting is rewarded by judges. NEVER hide a mocked feature.

| Feature | Status | Notes |
|---|---|---|
| RSS feed collection | ✅ Done | `collector/collect.py` live run 2026-10-23: 83 items fetched, 15 business facts saved to DB (si: 4, ta: 5, en: 6) |
| Tamil RSS feed search | ✅ Done | 2026-10-23: Found Tamil Mirror (2 feeds) + Thinakaran. Virakesari/Uthayan have no RSS. |
| Text cleaning (HTML, Unicode NFC) | ✅ Done | `collector/cleaner.py` |
| Legacy Sinhala font detection | ✅ Done | `collector/cleaner.py` — detects and skips |
| Deduplication | ✅ Done | `collector/cleaner.py` — by link and headline similarity |
| Language detection | ✅ Done | `collector/filter.py` — Unicode-range heuristic + langdetect fallback |
| Section filter (drop sports/entertainment) | ✅ Done | `collector/filter.py` — `section_filter()` |
| Keyword filter (Stage 4) | ✅ Done | `collector/filter.py` — `keyword_filter()` uses `data/keywords/business_keywords.yaml` |
| Pipeline wired (collect → clean → filter → save) | ✅ Done | `collector/collect.py` — full Stages 1–4 connected; Stage 5 hooks in when `extractor.py` is ready |
| LLM extraction (Stage 5) | ✅ Done | `collector/extractor.py` — supports Gemini, OpenAI, & multilingual fallback; backfill completed |
| SQLite database schema | ✅ Done | `database/db.py` — schema and query helpers; populated with initial 15 news facts |
| Vector store (ChromaDB) | ❌ Not started | For semantic / cross-lingual search |
| Agent loop | ✅ Done | `agent/loop.py` — multilingual perceive (si/ta/en), dynamic decide, national fallback, & conflict detection |
| search_news tool | ✅ Ready | `agent/tools/search.py` — queries DB; initial news items now available |
| compute_trend tool | ✅ Ready | `agent/tools/trend.py` — logic done; can run against DB data |
| write_report tool | ✅ Done | `agent/tools/report.py` — full structure; generates from evidence |
| Streamlit interface | ✅ Done | `interface/app.py` — full UI with confidence badge, opportunities/risks, evidence links, disclaimer |
| Evaluation label tool | ✅ Done | `evaluation/label_tool.py` — `--export`, `--label`, `--stats` modes; ready to export DB rows |
| Hand-labelled Sinhala headlines | ❌ Not started | Target: 50; needs collector to run first |
| Hand-labelled Tamil headlines | ❌ Not started | Target: 50; needs collector to run first (feeds now available) |
| Evaluation (precision/recall) | ❌ Not started | Needs hand-labelled data and LLM extractor |
| User interviews | ❌ Not started | Target: 3-5 business owners before proposal submission |

## Feed Status

Last tested: **2026-10-23** (Tamil investigation) | **2026-10-22** (Sinhala/English)

| Outlet | Language | Status | Notes |
|---|---|---|---|
| Ada Derana Sinhala | si | ✅ Verified | 2026-10-22 — 25 items |
| Dinamina | si | ✅ Verified | 2026-10-22 — 10 items |
| Mawbima | si | ✅ Verified | 2026-10-22 — 10 items |
| Lanka C News | si | ✅ Verified | 2026-10-22 — 10 items. Tabloid-style — lower credibility weight |
| Lankadeepa | si | ⚠️ Empty | 2026-10-22 — HTTP 200 but 0 items. Try /rss/business or /rss/economy |
| Siyatha News | si | ⚠️ Empty | 2026-10-22 — HTTP 200 but 0 items. BIAS: many China-related stories |
| Divaina | si | ⚠️ Empty | 2026-10-22 — HTTP 200 but 0 items. May use legacy Sinhala font |
| Ada (ada.lk) | si | ⚠️ Empty | 2026-10-22 — HTTP 200 but 0 items. Try /feed or /rss.xml |
| Newsfirst Sinhala | si | ⛔ Blocked | 2026-10-22 — HTTP 403 |
| Lanka Truth | si | ⛔ Blocked | 2026-10-22 — HTTP 401. Requires login — skip |
| Neth News | si | ⛔ Dead | 2026-10-22 — HTTP 404 |
| Tamil Guardian | ta | ✅ Verified | 2026-10-22 — 9 items. International/diaspora focus |
| Tamil Mirror (News) | ta | ✅ **NEW** Verified | **2026-10-23 — 12 items.** URL: `/rss/news/175`. Real Tamil content confirmed |
| Tamil Mirror (Business) | ta | ✅ **NEW** Verified | **2026-10-23 — 12 items.** URL: `/rss/business/50`. Business section |
| Thinakaran | ta | ✅ **NEW** Verified | **2026-10-23 — 10 items.** URL: `/feed/` (WordPress site). Tamil headlines confirmed |
| Virakesari | ta | ⛔ Dead | **2026-10-23 — No RSS.** /rss=404, /feed/=500. No public feed. Scraping needed |
| Thinakkural | ta | ⛔ Blocked | **2026-10-23 — Infinite redirect loop** on /feed/. Re-test later |
| Uthayan | ta | ⛔ Dead | **2026-10-23 — HTTP 404, SSL cert expired.** Site may be defunct |
| Ada Derana English | en | ✅ Verified | 2026-10-22 — 25 items |
| Lanka Business Online | en | ✅ Verified | 2026-10-22 — 10 items. Check for Sri Lanka-relevant content |
| Daily FT | en | ⚠️ Empty | 2026-10-22 — HTTP 200 but 0 items. Try /rss/business or /rss.xml |
| Daily Mirror | en | ⚠️ Empty | 2026-10-22 — HTTP 200 but 0 items. Try /rss.xml or section feed |
| EconomyNext | en | ⛔ Blocked | 2026-10-22 — HTTP 403. Best English business source — try mobile hotspot |

## Cost Tracking

| Item | Estimate | Actual (fill in after testing) |
|---|---|---|
| LLM calls per 1,000 headlines | TBD | — |
| LLM calls per agent question | TBD | — |
| Embedding cost per 1,000 items | $0 (local model) | — |
| Filter hit rate (headlines passing keyword filter) | TBD | — |
