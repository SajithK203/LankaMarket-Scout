"""
interface/app.py
----------------
LankaMarket Scout — Streamlit web interface.
Member C owns this file.

Run:
    streamlit run interface/app.py
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
    st.markdown("**Scope (Prototype)**")
    st.markdown("- Districts: Kandy, Anuradhapura, Galle")
    st.markdown("- Sectors: Agriculture, Food Retail")
    st.markdown("- Languages: Sinhala, Tamil, English")
    st.divider()
    st.warning("Decision support only. Not financial advice.")

# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("LankaMarket Scout")
st.subheader("Evidence-based market intelligence for small businesses")

st.info(
    "Ask about a business opportunity in Sri Lanka. "
    "The agent will search recent local news in Sinhala, Tamil and English "
    "and give you a structured report with sources and confidence levels.",
    icon="💡"
)

# Question input
question = st.text_area(
    "Your question (Sinhala, Tamil or English):",
    placeholder="Example: I want to open a small cafe in Kandy. Is it a good idea now?",
    height=100,
)

col1, col2 = st.columns(2)
with col1:
    submitted = st.button("🔍 Analyse", type="primary", use_container_width=True)
with col2:
    clear = st.button("🗑️ Clear", use_container_width=True)

if clear:
    st.rerun()

# ── Agent response ────────────────────────────────────────────────────────────
if submitted and question.strip():
    with st.spinner("Agent is researching... (this may take a moment)"):
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
    st.subheader("📋 Report")

    # Confidence badge
    conf = report.get("confidence", {})
    conf_label = conf.get("label", "Unknown")
    conf_color = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(conf_label, "⚪")
    st.markdown(f"**Confidence:** {conf_color} {conf_label} — {conf.get('reason', '')}")

    # Summary
    st.markdown("### Summary")
    st.write(report.get("summary", "No summary available."))

    # Opportunities and Risks side by side
    col_opp, col_risk = st.columns(2)

    with col_opp:
        st.markdown("### ✅ Opportunities")
        opps = report.get("opportunities", [])
        if opps:
            for o in opps:
                src = o["source"]
                st.markdown(f"- {o['point']}")
                st.caption(f"  [{src['outlet']}]({src['link']}) — {src.get('published_at', '')}")
        else:
            st.write("No positive signals found in recent news.")

    with col_risk:
        st.markdown("### ⚠️ Risks")
        risks = report.get("risks", [])
        if risks:
            for r in risks:
                src = r["source"]
                st.markdown(f"- {r['point']}")
                st.caption(f"  [{src['outlet']}]({src['link']}) — {src.get('published_at', '')}")
        else:
            st.write("No negative signals found in recent news.")

    # Evidence list
    with st.expander("📰 Evidence used (all sources)"):
        evidence = report.get("evidence_list", [])
        if evidence:
            for e in evidence:
                direction_icon = {"positive": "✅", "negative": "❌", "mixed": "🔀"}.get(e["direction"], "•")
                st.markdown(
                    f"{direction_icon} [{e['headline']}]({e['link']}) "
                    f"— {e['outlet']} ({e['published']})"
                )
                if e.get("summary"):
                    st.caption(f"  {e['summary']}")
        else:
            st.write("No evidence items (database may be empty — run the collector first).")

    # What to check next
    with st.expander("🔍 What to verify next (in person)"):
        for item in report.get("check_next", []):
            st.markdown(f"- {item}")

    # Disclaimer — always visible
    st.divider()
    st.error(report.get("disclaimer", ""))

elif submitted:
    st.warning("Please enter a question first.")
