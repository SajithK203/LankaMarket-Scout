"""
agent/loop.py
-------------
The agent decision loop — the core of LankaMarket Scout.

Matches the competition booklet's Perceive → Decide → Act → Loop architecture:
  1. PERCEIVE  — parse the user's natural language question into structured parameters
  2. DECIDE    — determine the next tool call based on current plan & gathered evidence
  3. ACT       — execute the chosen tool (search_news, compute_trend, or finish)
  4. LOOP      — aggregate evidence, detect contradictory signals, adjust plan until done

Member B owns this file.
"""

import json
import logging
import re
from typing import Any

from agent.tools.search import search_news
from agent.tools.trend import compute_trend
from agent.tools.report import write_report
from collector.extractor import (
    load_llm_config,
    VALID_DISTRICTS,
    DISTRICT_LOOKUP_SI,
    DISTRICT_LOOKUP_TA,
    VALID_SECTORS,
    _clean_json_response,
)

log = logging.getLogger(__name__)

MAX_STEPS = 6  # hard cap — prevents infinite loops and cost blowout

TOOLS = {
    "search_news": search_news,
    "compute_trend": compute_trend,
}

PLAN_SYSTEM_PROMPT = """You are an expert market intelligence planner for Sri Lanka micro and SME enterprises.
The user will ask a business question in Sinhala, Tamil, or English.
Analyze the question and extract the relevant Sri Lankan districts, business sectors, and investigation focus.

Valid districts:
["Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo", "Galle", "Gampaha", "Hambantota", "Jaffna", "Kalutara", "Kandy", "Kegalle", "Kilinochchi", "Kurunegala", "Mannar", "Matale", "Matara", "Monaragala", "Mullaitivu", "Nuwara Eliya", "Polonnaruwa", "Puttalam", "Ratnapura", "Trincomalee", "Vavuniya", "national"]
If no specific district is mentioned, use ["national"].

Valid sectors:
["agriculture", "food_retail", "tourism", "transport", "construction", "services", "energy", "manufacturing", "logistics", "finance", "other"]

Respond ONLY with valid JSON in this schema:
{
  "districts": ["Kandy"],
  "sectors": ["food_retail"],
  "days": 90,
  "focus": "Brief description of the user's goal and focus areas"
}
"""


def _heuristic_plan(question: str) -> dict:
    """Heuristic planning when LLM API keys are not available."""
    text = question.lower()

    # Detect districts
    districts = set()
    for d in VALID_DISTRICTS:
        if d != "national" and re.search(r"\b" + re.escape(d.lower()) + r"\b", text):
            districts.add(d)

    for word, d in DISTRICT_LOOKUP_SI.items():
        if word in question:
            districts.add(d)

    for word, d in DISTRICT_LOOKUP_TA.items():
        if word in question:
            districts.add(d)

    final_districts = list(districts) if districts else ["national"]

    # Detect sectors
    sectors = set()
    if any(k in text for k in ["agri", "paddy", "rice", "tea", "crop", "farm", "ගොවි", "තේ", "වී", "விவசாய", "தேயிலை"]):
        sectors.add("agriculture")
    if any(k in text for k in ["cafe", "restaurant", "food", "retail", "shop", "palm oil", "කැෆේ", "ආහාර", "තෙල්", "உணவு", "கடை"]):
        sectors.add("food_retail")
    if any(k in text for k in ["touris", "hotel", "guest", "resort", "හෝටල්", "සංචාරක", "சுற்றுலா"]):
        sectors.add("tourism")
    if any(k in text for k in ["gas", "litro", "fuel", "petrol", "diesel", "solar", "power", "electricity", "ගෑස්", "විදුලි", "எரிபொருள்", "மின்சாரம்"]):
        sectors.add("energy")
    if any(k in text for k in ["transport", "delivery", "vehicle", "bus", "lorry", "වාහන", "ප්‍රවාහන", "போக்குவரத்து"]):
        sectors.add("transport")
    if any(k in text for k in ["bank", "loan", "tax", "vat", "ණය", "බදු", "வங்கி"]):
        sectors.add("finance")

    final_sectors = list(sectors) if sectors else ["food_retail"]

    return {
        "districts": final_districts,
        "sectors": final_sectors,
        "days": 90,
        "focus": f"Investigating opportunities and risks for {', '.join(final_sectors)} in {', '.join(final_districts)}",
    }


def llm_plan(question: str) -> dict:
    """
    PERCEIVE step: Ask LLM (or heuristic) to parse question into districts, sectors, and parameters.
    """
    cfg = load_llm_config()
    if cfg.get("api_key"):
        try:
            if cfg["provider"] == "gemini":
                import google.generativeai as genai
                genai.configure(api_key=cfg["api_key"])
                model = genai.GenerativeModel(
                    model_name=cfg.get("model", "gemini-1.5-flash"),
                    generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
                )
                prompt = f"{PLAN_SYSTEM_PROMPT}\n\nUser Question:\n{question}"
                resp = model.generate_content(prompt)
                plan = _clean_json_response(resp.text)
                if plan.get("districts") and plan.get("sectors"):
                    plan.setdefault("days", 90)
                    return plan
            elif cfg["provider"] == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=cfg["api_key"])
                resp = client.chat.completions.create(
                    model=cfg.get("model", "gpt-4o-mini"),
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                        {"role": "user", "content": question},
                    ],
                )
                raw = resp.choices[0].message.content or "{}"
                plan = _clean_json_response(raw)
                if plan.get("districts") and plan.get("sectors"):
                    plan.setdefault("days", 90)
                    return plan
        except Exception as e:
            log.warning(f"LLM plan error: {e}. Falling back to heuristic planner.")

    return _heuristic_plan(question)


def llm_decide(plan: dict, evidence: list) -> dict:
    """
    DECIDE step: Determine the next tool call given current evidence.
    Follows deliberate reasoning:
      1. Primary search with planned district & sectors.
      2. If 0 items found and district wasn't 'national', expand to national scope.
      3. Compute statistical trend.
      4. Finish when sufficient evidence collected.
    """
    step = len(evidence)

    # Step 0: Search planned district & sector
    if step == 0:
        return {
            "type": "tool",
            "tool": "search_news",
            "args": {
                "districts": plan.get("districts", ["national"]),
                "sectors": plan.get("sectors", ["food_retail"]),
                "days": plan.get("days", 90),
            },
        }

    # Analyze first search results
    first_result = evidence[0].get("result", {})
    item_count = first_result.get("count", 0)

    # Step 1: If specific district had 0 items, expand search to national scope
    if step == 1:
        if item_count == 0 and "national" not in plan.get("districts", []):
            log.info("District-specific search yielded 0 items; broadening search to national scope.")
            return {
                "type": "tool",
                "tool": "search_news",
                "args": {
                    "districts": ["national"],
                    "sectors": plan.get("sectors", ["food_retail"]),
                    "days": plan.get("days", 90),
                },
            }
        else:
            return {
                "type": "tool",
                "tool": "compute_trend",
                "args": {
                    "districts": plan.get("districts", ["national"]),
                    "sectors": plan.get("sectors", ["food_retail"]),
                    "days": plan.get("days", 90),
                },
            }

    # Step 2: If we broadened search in Step 1, compute trend now
    if step == 2:
        has_trend = any(e.get("action", {}).get("tool") == "compute_trend" for e in evidence)
        if not has_trend:
            return {
                "type": "tool",
                "tool": "compute_trend",
                "args": {
                    "districts": ["national"],
                    "sectors": plan.get("sectors", ["food_retail"]),
                    "days": plan.get("days", 90),
                },
            }

    return {"type": "finish"}


def has_conflict(evidence: list) -> bool:
    """
    Check if gathered evidence contains contradictory directions
    (e.g. positive supply signals vs negative cost/regulation signals).
    """
    items = []
    for e in evidence:
        res = e.get("result", {})
        if isinstance(res, dict) and "items" in res:
            items.extend(res["items"])

    directions = {i.get("direction") for i in items if i.get("direction")}
    return "positive" in directions and "negative" in directions


def run_agent(question: str, user_profile: dict | None = None) -> dict:
    """
    Main entry point. Runs the full Perceive → Decide → Act → Loop cycle.

    Args:
        question: the user's natural-language question
        user_profile: optional dict with budget, timeframe, risk_comfort

    Returns:
        A report dict with keys: summary, opportunities, risks, evidence, confidence, check_next
    """
    # ── 1. PERCEIVE ───────────────────────────────────────────────────
    plan = llm_plan(question)
    log.info(f"Agent plan: {plan}")
    evidence = []

    # ── 2. LOOP (Decide → Act) ────────────────────────────────────────
    for step in range(MAX_STEPS):
        action = llm_decide(plan, evidence)

        if action["type"] == "ask_user":
            return {"type": "ask_user", "question": action["question"]}

        if action["type"] == "finish":
            break

        tool_fn = TOOLS.get(action["tool"])
        if tool_fn is None:
            break

        result = tool_fn(**action["args"])
        evidence.append({"action": action, "result": result})

        # Check for conflicting evidence
        if has_conflict(evidence):
            plan["conflict_detected"] = True

    # ── 3. WRITE REPORT ───────────────────────────────────────────────
    report = write_report(question=question, evidence=evidence, plan=plan)
    return report


if __name__ == "__main__":
    test_questions = [
        "I want to open a small cafe in Kandy. Is it a good idea now?",
        "මම ගාල්ලේ සංචාරක හෝටලයක් පටන් ගන්න බලාපොරොත්තු වෙනවා. අවදානම් මොනවාද?",
        "கொழும்பில் புதிய உணவகம் அல்லது எரிபொருள் விநியோக நிலைமை எவ்வாறு உள்ளது?",
    ]

    for q in test_questions:
        print("\n" + "=" * 70)
        print(f"QUESTION: {q}")
        p = llm_plan(q)
        print(f"PARSED PLAN: districts={p['districts']}, sectors={p['sectors']}")
        rep = run_agent(q)
        print(f"CONFIDENCE: {rep['confidence']['label']} ({rep['confidence']['score']})")
        print(f"SUMMARY: {rep['summary']}")
        print(f"EVIDENCE COUNT: {len(rep.get('evidence_list', []))}")
