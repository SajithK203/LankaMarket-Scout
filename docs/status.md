# status.md — Feature Status Report
# Update this table every time something changes.
# Honest reporting is rewarded by judges. NEVER hide a mocked feature.

| Feature | Status | Notes |
|---|---|---|
| RSS feed collection | 🔄 In Progress | `scripts/check_feeds.py` written; feeds not yet verified from our network |
| Text cleaning (HTML, Unicode NFC) | ✅ Done | `collector/cleaner.py` |
| Legacy Sinhala font detection | ✅ Done | `collector/cleaner.py` — detects and skips |
| Deduplication | ✅ Done | `collector/cleaner.py` — by link and headline similarity |
| Language detection | ✅ Done | `collector/filter.py` — Unicode-range heuristic + langdetect fallback |
| Section filter (drop sports/entertainment) | ✅ Done | `collector/filter.py` — `section_filter()` |
| Keyword filter (Stage 4) | ✅ Done | `collector/filter.py` — `keyword_filter()` uses `data/keywords/business_keywords.yaml` |
| Pipeline wired (collect → clean → filter → save) | ✅ Done | `collector/collect.py` — full Stages 1–4 connected; Stage 5 hooks in when `extractor.py` is ready |
| LLM extraction (Stage 5) | ❌ Not started | `collector/extractor.py` to be built by Member B; pipeline will skip gracefully until ready |
| SQLite database schema | ✅ Done | `database/db.py` — schema and query helpers |
| Vector store (ChromaDB) | ❌ Not started | For semantic / cross-lingual search |
| Agent loop | 🟡 Mocked | `agent/loop.py` — structure complete; LLM calls are mocked (Member B to implement) |
| search_news tool | 🟡 Mocked | `agent/tools/search.py` — queries DB; DB is empty until collector runs |
| compute_trend tool | 🟡 Mocked | `agent/tools/trend.py` — logic done; depends on real data |
| write_report tool | ✅ Done | `agent/tools/report.py` — full structure; generates from evidence |
| Streamlit interface | ✅ Done | `interface/app.py` — full UI with confidence badge, opportunities/risks, evidence links, disclaimer |
| Evaluation label tool | ✅ Done | `evaluation/label_tool.py` — `--export`, `--label`, `--stats` modes; reads from DB |
| Hand-labelled Sinhala headlines | ❌ Not started | Target: 50; needs collector to run first |
| Hand-labelled Tamil headlines | ❌ Not started | Target: 50; needs Tamil feeds working |
| Evaluation (precision/recall) | ❌ Not started | Needs hand-labelled data and LLM extractor |
| User interviews | ❌ Not started | Target: 3-5 business owners before proposal submission |

## Feed Status

| Outlet | Language | Status | Notes |
|---|---|---|---|
| Lankadeepa | si | 🔄 Unverified | Test from our network — `python scripts/check_feeds.py --lang si` |
| Neth News | si | 🔄 Unverified | Test |
| Siyatha News | si | 🔄 Unverified | BIAS: many China-related stories |
| Lanka Truth | si | 🔄 Unverified | BIAS: politically partisan |
| Lanka C News | si | 🔄 Unverified | Tabloid-style |
| Ada Derana Sinhala | si | ⛔ Blocked (cloud) | Test from home/mobile hotspot |
| Dinamina | si | ⛔ Blocked (cloud) | Test from home/mobile hotspot |
| Divaina | si | ⛔ Blocked (cloud) | May use legacy Sinhala font — check |
| Ada (ada.lk) | si | ⛔ Blocked | Was returning 403 on 14 Oct; re-test |
| Newsfirst Sinhala | si | ⛔ Blocked (cloud) | Test from home/mobile hotspot |
| Mawbima | si | ⛔ Blocked (cloud) | Test from home/mobile hotspot |
| Virakesari | ta | ❓ No URL | Find RSS URL first — search `virakesari.lk rss` |
| Thinakaran | ta | ❓ No URL | Find RSS URL — search `thinakaran.lk rss` |
| Thinakkural | ta | ❓ No URL | Find RSS URL |
| Uthayan | ta | ❓ No URL | Find RSS URL |
| Tamil Guardian | ta | 🔄 Unverified | URL set; test it |
| Tamil Mirror | ta | ❓ No URL | Find RSS URL |
| EconomyNext | en | 🔄 Unverified | Best English source |
| Lanka Business Online | en | 🔄 Unverified | Test |
| Daily FT | en | 🔄 Unverified | Test |
| Daily Mirror | en | 🔄 Unverified | Test |
| Ada Derana English | en | 🔄 Unverified | Test |

## Cost Tracking

| Item | Estimate | Actual (fill in after testing) |
|---|---|---|
| LLM calls per 1,000 headlines | TBD | — |
| LLM calls per agent question | TBD | — |
| Embedding cost per 1,000 items | $0 (local model) | — |
| Filter hit rate (headlines passing keyword filter) | TBD | — |
