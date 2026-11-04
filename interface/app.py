"""
interface/app.py
----------------
LankaMarket Scout — Streamlit web interface.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LankaMarket Scout",
    page_icon="🇱🇰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🇱🇰 LankaMarket Scout")
    st.caption("AI agent for Sri Lankan small-business intelligence")
    st.divider()
    
    st.subheader("🔄 Live News Feed")
    if st.button("Fetch Latest News Feeds", use_container_width=True):
        with st.spinner("Polling live RSS feeds across Sri Lanka..."):
            try:
                from collector.collect import collect_all
                collected = collect_all(dry_run=False)
                st.success(f"Fetched & synced {len(collected)} news items into database!")
            except Exception as e:
                st.error(f"Live fetch notice: {e}")
                
    st.divider()
    st.markdown("**Scope & Capabilities**")
    st.markdown("- **Languages**: Sinhala, Tamil, English")
    st.markdown("- **Sectors**: Food/Retail, Agriculture, Tourism, Energy, Manufacturing, Transport, Finance")
    st.markdown("- **Districts**: Island-wide & localized (Kandy, Colombo, Galle, etc.)")
    st.divider()
    st.warning("⚠️ Decision support only. Not financial advice.")

# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("LankaMarket Scout")
st.subheader("Evidence-based market intelligence for small businesses")

st.info(
    "Ask any business or market question about Sri Lanka in English, Sinhala, or Tamil. "
    "The AI agent queries local news facts across native sources and synthesizes actionable recommendations.",
    icon="💡"
)

# Question input
question = st.text_area(
    "Your question (Sinhala, Tamil or English):",
    placeholder="Example: I want to open a small bakery or restaurant in Kandy. What are the food prices and risks?",
    height=90,
)

col1, col2 = st.columns([1, 1])
with col1:
    submitted = st.button("🔍 Analyse", type="primary", use_container_width=True)
with col2:
    clear = st.button("🗑️ Clear", use_container_width=True)

if clear:
    st.rerun()

# ── Agent response ────────────────────────────────────────────────────────────
if submitted and question.strip():
    with st.spinner("Agent is researching evidence & synthesizing recommendations..."):
        try:
            from agent.loop import run_agent
            report = run_agent(question)
        except Exception as e:
            st.error(f"Agent error: {e}")
            st.stop()

    if report.get("type") == "ask_user":
        st.warning(f"The agent needs more information: **{report['question']}**")
        st.stop()

    # ── Report display ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📋 Market Intelligence Report")

    # Confidence badge
    conf = report.get("confidence", {})
    conf_label = conf.get("label", "Unknown")
    conf_color = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(conf_label, "⚪")
    st.markdown(f"**Confidence:** {conf_color} **{conf_label}** — *{conf.get('reason', '')}*")

    # Summary
    st.markdown("### Executive Summary")
    st.write(report.get("summary", "No summary available."))

    # Strategic Recommendations (AI Generated)
    recommendations = report.get("recommendations", [])
    if recommendations:
        st.markdown("### 💡 Strategic Recommendations")
        for rec in recommendations:
            st.markdown(f"- **{rec}**")

    # Opportunities and Risks side by side
    col_opp, col_risk = st.columns(2)

    with col_opp:
        st.markdown("### ✅ Opportunities")
        opps = report.get("opportunities", [])
        if opps:
            for o in opps:
                st.markdown(f"- {o['point']}")
                src = o.get("source")
                if src and src.get("link"):
                    st.caption(f"  [{src.get('outlet', 'Source')}]({src['link']}) — {src.get('published_at', '')}")
        else:
            st.write("No direct positive signals found in recent local news.")

    with col_risk:
        st.markdown("### ⚠️ Key Risks")
        risks = report.get("risks", [])
        if risks:
            for r in risks:
                st.markdown(f"- {r['point']}")
                src = r.get("source")
                if src and src.get("link"):
                    st.caption(f"  [{src.get('outlet', 'Source')}]({src['link']}) — {src.get('published_at', '')}")
        else:
            st.write("No direct negative signals found in recent local news.")

    # Evidence list
    with st.expander("📰 Ground Evidence Used (Cited Local Sources)"):
        evidence = report.get("evidence_list", [])
        if evidence:
            for e in evidence:
                direction_icon = {"positive": "✅", "negative": "❌", "mixed": "🔀"}.get(e.get("direction"), "•")
                st.markdown(
                    f"{direction_icon} [{e['headline']}]({e['link']}) "
                    f"— *{e['outlet']}* ({e.get('published')})"
                )
                if e.get("summary"):
                    st.caption(f"  {e['summary']}")
        else:
            st.write("No evidence items matched this specific query in the current database.")

    # What to check next
    with st.expander("🔍 On-the-Ground Verification Checklist"):
        for item in report.get("check_next", []):
            st.markdown(f"- {item}")

    # Disclaimer — always visible
    st.divider()
    st.caption(report.get("disclaimer", ""))

elif submitted:
    st.warning("Please enter a question first.")
