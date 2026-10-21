# 🇱🇰 LankaMarket Scout

> An AI agent that reads Sri Lankan news in Sinhala, Tamil and English and turns it into evidence-based advice for small businesses.

**Competition:** InnovaX 1.0 — Domain C: Civic Services and Community Wellbeing  
**Status:** Phase 1 — Planning / Feasibility  
**Last updated:** 2026-10-21

---

## What it does

A small-business owner types a question like *"Is it a good time to open a café in Kandy?"* — the agent searches recent local news in all three languages, cross-checks sources, detects conflicts, and returns a structured report with opportunities, risks, evidence links, and a confidence level.

## Quick start (for developers)

```bash
# 1. Clone and enter the repo
git clone https://github.com/<your-org>/LankaMarket-Scout
cd LankaMarket-Scout

# 2. Create virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and fill in config
cp config/settings.example.yaml config/settings.yaml
# Edit config/settings.yaml — add your LLM API key

# 5. Test feeds
python scripts/check_feeds.py

# 6. Run one collection cycle (dry run)
python -m collector.collect --dry-run

# 7. Launch the interface
streamlit run interface/app.py
```

## Folder structure

```
LankaMarket-Scout/
├── collector/          # Feed fetching, cleaning, deduplication
├── agent/              # Agent loop + tools
│   └── tools/          # Individual tool implementations
├── database/           # DB schema, vector store helpers
├── interface/          # Streamlit web UI
├── data/
│   ├── feeds/          # sources.yaml — list of RSS feeds
│   ├── labels/         # Hand-labelled headlines for evaluation
│   ├── keywords/       # Business keyword lists (3 languages)
│   └── gazetteer/      # District / place-name lookup table
├── evaluation/         # Accuracy measurement scripts
├── scripts/            # One-off helper scripts
├── tests/              # Unit tests
├── config/             # Settings and API keys (never commit keys!)
└── docs/               # Architecture diagrams, reports
```

## Credits

- [sinhala-news-corpus](https://github.com/dhananjaya-hbc/sinhala-news-corpus) — MIT licence — feed collection approach and cleaning rules
- Sri Lanka Document Datasets — historical news corpus
- lk_news collection — 130,000+ news documents 2021–2026
- All news outlets whose RSS feeds we read — headlines and links only, no full-text copying

## Responsible AI

This tool provides decision **support** only. It is not financial advice. Every claim is linked to a source. The agent never takes any real-world action without explicit user confirmation.

---

## Team

| Member | Role |
|--------|------|
| Member A | Data & pipeline |
| Member B | AI & agent |
| Member C | Product, interface & docs |
