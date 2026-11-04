"""
agent/tools/report.py
---------------------
Tool 3: write_report
Takes all accumulated evidence and produces the final structured report.
Uses Gemini LLM to synthesize actionable business recommendations,
tailored opportunities, and operational risks grounded in cited news evidence.
"""

import json
import logging
import re
from datetime import datetime
from collector.extractor import load_llm_config, _clean_json_response

log = logging.getLogger(__name__)

DISCLAIMER = (
    "⚠️ IMPORTANT: This report is for decision support only. "
    "It is not financial advice. Always verify key facts on the ground "
    "before investing. The agent's conclusions depend on the news it "
    "could find — if sources are biased or incomplete, the report may be too."
)


def map_confidence(score: float) -> str:
    """Convert a 0–1 float to a human-readable confidence label."""
    if score >= 0.75:
        return "High"
    elif score >= 0.45:
        return "Medium"
    else:
        return "Low"


SYNTHESIS_SYSTEM_PROMPT = """You are an expert economic analyst and small-business advisor in Sri Lanka.
Analyze the user's specific business question and the cited news items collected from local sources.
Synthesize an actionable, realistic business intelligence assessment formatted strictly as a single JSON object.

Output JSON fields:
{
  "summary": "2-3 clear sentences directly answering the user's question based on the evidence.",
  "opportunities": [
    "Specific opportunity 1 with concrete reasoning for this venture",
    "Specific opportunity 2"
  ],
  "risks": [
    "Specific risk 1 (costs, fuel, electricity, regulations, or supply)",
    "Specific risk 2"
  ],
  "recommendations": [
    "Actionable step 1 for the business owner",
    "Actionable step 2"
  ],
  "check_next": [
    "On-the-ground verification item 1",
    "On-the-ground verification item 2"
  ]
}

Safety rule: Do NOT invent statistics or cite facts not supported by the evidence. If evidence is scarce or not directly about the product, explicitly state that in the summary and suggest verifying local suppliers directly.
Respond ONLY with valid JSON.
"""


def _synthesize_with_llm(question: str, items: list[dict], plan: dict) -> dict | None:
    """Call Gemini LLM to generate recommendations and analysis from evidence."""
    cfg = load_llm_config()
    if not cfg.get("api_key"):
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=cfg["api_key"])
        model_name = cfg.get("model", "models/gemini-3.5-flash-lite")
        if not model_name.startswith("models/"):
            model_name = "models/" + model_name

        evidence_text = "\n".join([
            f"- [{i.get('outlet')}] {i.get('headline')} (Summary: {i.get('summary_en', '')}, Direction: {i.get('direction', 'mixed')})"
            for i in items[:10]
        ])

        prompt = (
            f"{SYNTHESIS_SYSTEM_PROMPT}\n\n"
            f"User Question: {question}\n"
            f"Planned Scope: Districts={plan.get('districts')}, Sectors={plan.get('sectors')}\n\n"
            f"Gathered News Evidence ({len(items)} items):\n{evidence_text if items else 'No direct news items found in database.'}\n"
        )

        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        return _clean_json_response(resp.text)
    except Exception as e:
        log.warning(f"LLM synthesis error: {e}. Falling back to rule-based report.")
        return None


def write_report(question: str, evidence: list, plan: dict) -> dict:
    """
    Produce the final report from accumulated evidence.
    """
    # Collect all news items from search results
    all_items = []
    trend_result = None

    for entry in evidence:
        result = entry.get("result", {})
        tool = entry.get("action", {}).get("tool", "")

        if tool == "search_news":
            all_items.extend(result.get("items", []))
        elif tool == "compute_trend":
            trend_result = result

    # Deduplicate items by link
    seen_links = set()
    unique_items = []
    for item in all_items:
        if item["link"] not in seen_links:
            seen_links.add(item["link"])
            unique_items.append(item)

    # Separate into opportunities and risks with business cost intelligence
    raw_opps = []
    raw_risks = []
    for i in unique_items:
        hl = (i.get("headline", "") + " " + i.get("summary_en", "")).lower()
        # Price cuts / reductions in fuel/gas/energy are positive input cost opportunities
        if any(w in hl for w in ["cut", "cuts", "slash", "slashes", "drop", "drops", "reduce", "reduces", "eases"]) and any(c in hl for c in ["price", "prices", "gas", "fuel", "tariff"]):
            raw_opps.append(i)
        elif i.get("direction") == "positive":
            raw_opps.append(i)
        else:
            raw_risks.append(i)

    # Determine overall confidence
    if trend_result and len(unique_items) >= 3:
        conf_score = trend_result["confidence"]
        conflict_note = ""
        if plan.get("conflict_detected"):
            conf_score = max(conf_score - 0.2, 0.1)
            conflict_note = "Conflicting sources detected — confidence reduced."
    elif len(unique_items) > 0:
        conf_score = 0.4
        conflict_note = "Limited directly relevant news facts in database."
    else:
        conf_score = 0.15
        conflict_note = "No specific news articles found for this topic."

    conf_label = map_confidence(conf_score)
    conf_reason = (
        f"{len(unique_items)} source(s) found. "
        f"Trend: {trend_result['trend'] if trend_result else 'insufficient_data'}. "
        + conflict_note
    )

    # Build evidence list for display
    evidence_list = [
        {
            "headline": i["headline"],
            "outlet": i["outlet"],
            "published": i.get("published_at", "recent"),
            "link": i["link"],
            "summary": i.get("summary_en", ""),
            "direction": i.get("direction", "mixed"),
        }
        for i in unique_items
    ]

    # Try AI synthesis first
    ai_analysis = _synthesize_with_llm(question, unique_items, plan)

    if ai_analysis and ai_analysis.get("summary"):
        summary = ai_analysis["summary"]
        opp_list = [
            {"point": opt, "source": unique_items[idx % len(unique_items)] if unique_items else None}
            for idx, opt in enumerate(ai_analysis.get("opportunities", []))
        ]
        risk_list = [
            {"point": rsk, "source": unique_items[idx % len(unique_items)] if unique_items else None}
            for idx, rsk in enumerate(ai_analysis.get("risks", []))
        ]
        recommendations = ai_analysis.get("recommendations", [])
        check_next = ai_analysis.get("check_next", [
            "Visit the target locality and observe customer footfall.",
            "Contact local wholesale ingredient/raw material suppliers for firm quotes.",
            "Check municipal/Pradeshiya Sabha commercial license requirements.",
        ])
    else:
        # Fallback template
        districts_str = ", ".join(plan.get("districts", ["Sri Lanka"]))
        sectors_str = ", ".join(plan.get("sectors", ["general business"]))
        trend_str = trend_result["trend"] if trend_result else "unclear"

        summary = (
            f"Based on {len(unique_items)} recent news items for {sectors_str} in {districts_str}, "
            f"the overall trend is {trend_str}. Found {len(raw_opps)} positive and {len(raw_risks)} risk signal(s). "
            f"{conf_reason}"
        )
        opp_list = [{"point": i.get("summary_en", i["headline"]), "source": i} for i in raw_opps]
        risk_list = [{"point": i.get("summary_en", i["headline"]), "source": i} for i in raw_risks]
        recommendations = [
            "Conduct preliminary ground research with existing sector operators.",
            "Monitor weekly fuel and electricity tariff adjustments.",
        ]
        check_next = [
            "Visit the area and talk to existing business owners.",
            "Ask suppliers about current input costs directly.",
            "Check local Pradeshiya Sabha permit requirements.",
        ]

    return {
        "question": question,
        "summary": summary,
        "opportunities": opp_list,
        "risks": risk_list,
        "recommendations": recommendations,
        "evidence_list": evidence_list,
        "confidence": {"label": conf_label, "score": round(conf_score, 2), "reason": conf_reason},
        "check_next": check_next,
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.utcnow().isoformat(),
    }
