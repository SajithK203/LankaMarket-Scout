"""
agent/tools/report.py
---------------------
Tool 3: write_report
Takes all accumulated evidence and produces the final structured report.

Safety rule: every claim in the report MUST be linked to at least one
stored news item. The remove_unsupported_claims() function enforces this.
"""

from datetime import datetime


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


def write_report(question: str, evidence: list, plan: dict) -> dict:
    """
    Produce the final report from accumulated evidence.

    Report structure:
      - question
      - summary (plain sentences)
      - opportunities (list of points with sources)
      - risks (list of points with sources)
      - evidence_list (all items used, with links)
      - confidence (Low / Medium / High + reason)
      - check_next (things the user should verify in person)
      - disclaimer (always shown)
      - generated_at (timestamp)
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

    # Separate into opportunities and risks
    opportunities = [i for i in unique_items if i["direction"] == "positive"]
    risks = [i for i in unique_items if i["direction"] in ("negative", "mixed")]

    # Determine overall confidence
    if trend_result:
        conf_score = trend_result["confidence"]
        conflict_note = ""
        if plan.get("conflict_detected"):
            conf_score = max(conf_score - 0.2, 0.1)
            conflict_note = "Conflicting sources detected — confidence reduced."
    else:
        conf_score = 0.3
        conflict_note = "Insufficient data for trend analysis."

    conf_label = map_confidence(conf_score)
    conf_reason = (
        f"{len(unique_items)} source(s) found. "
        f"Trend: {trend_result['trend'] if trend_result else 'unknown'}. "
        + conflict_note
    )

    # Build evidence list for display
    evidence_list = [
        {
            "headline": i["headline"],
            "outlet": i["outlet"],
            "published": i.get("published_at", "unknown date"),
            "link": i["link"],
            "summary": i.get("summary_en", ""),
            "direction": i["direction"],
        }
        for i in unique_items
    ]

    # Build summary text
    districts_str = ", ".join(plan.get("districts", ["unknown"]))
    sectors_str = ", ".join(plan.get("sectors", ["unknown"]))
    trend_str = trend_result["trend"] if trend_result else "unclear"

    summary = (
        f"Based on {len(unique_items)} recent news items for "
        f"{sectors_str} in {districts_str}, the overall outlook is {trend_str}. "
        f"There are {len(opportunities)} positive signal(s) and "
        f"{len(risks)} risk signal(s) in the evidence. "
        f"Confidence is {conf_label} — {conf_reason}"
    )

    # What to verify next (always shown)
    check_next = [
        "Visit the area and talk to existing business owners.",
        "Ask suppliers about current input costs directly.",
        "Check with the local Pradeshiya Sabha for permit requirements.",
        "Verify the most recent electricity and fuel prices.",
        "If opening a food business, confirm health inspection requirements.",
    ]

    return {
        "question": question,
        "summary": summary,
        "opportunities": [
            {"point": i.get("summary_en", i["headline"]), "source": i}
            for i in opportunities
        ],
        "risks": [
            {"point": i.get("summary_en", i["headline"]), "source": i}
            for i in risks
        ],
        "evidence_list": evidence_list,
        "confidence": {"label": conf_label, "score": round(conf_score, 2), "reason": conf_reason},
        "check_next": check_next,
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.utcnow().isoformat(),
    }
