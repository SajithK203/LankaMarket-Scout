"""
agent/loop.py
-------------
The agent decision loop — the core of LankaMarket Scout.

This is intentionally written as plain, readable Python (~60 lines)
so every team member can read, explain and modify it for the judges.

How it works (matches the competition booklet's Perceive → Decide → Act → Loop):
  1. PERCEIVE  — read the user's question
  2. DECIDE    — ask the LLM: what tool should I call next?
  3. ACT       — call that tool (search, trend, ask user, or finish)
  4. LOOP      — add the result to evidence; repeat until done or step limit hit
"""

from agent.tools.search import search_news
from agent.tools.trend import compute_trend
from agent.tools.report import write_report

MAX_STEPS = 6   # hard cap — prevents infinite loops and cost blowout

# Map tool names to actual functions
TOOLS = {
    "search_news": search_news,
    "compute_trend": compute_trend,
}


def llm_plan(question: str) -> dict:
    """
    Ask the LLM: what do we need to know to answer this question?
    Returns a plan dict with districts, sectors, focus areas.

    TODO (Member B): implement real LLM call using config/settings.yaml
    For now returns a mock plan so the loop structure can be tested.
    """
    # MOCK — replace with real LLM call
    return {
        "districts": ["Kandy"],
        "sectors": ["food_retail"],
        "days": 90,
        "focus": "input costs and demand signals",
    }


def llm_decide(plan: dict, evidence: list) -> dict:
    """
    Ask the LLM: given the plan and evidence so far, what is the next action?
    Returns {"type": "tool", "tool": "search_news", "args": {...}}
           or {"type": "ask_user", "question": "..."}
           or {"type": "finish"}

    TODO (Member B): implement real LLM call.
    This mock does two searches then finishes.
    """
    step = len(evidence)
    if step == 0:
        return {"type": "tool", "tool": "search_news",
                "args": {"districts": plan["districts"],
                         "sectors": plan["sectors"],
                         "days": plan["days"]}}
    if step == 1:
        return {"type": "tool", "tool": "compute_trend",
                "args": {"districts": plan["districts"],
                         "sectors": plan["sectors"],
                         "days": plan["days"]}}
    return {"type": "finish"}


def has_conflict(evidence: list) -> bool:
    """
    Check if any two evidence items contradict each other
    (e.g. one says 'positive', another says 'negative' for same sector+district).

    TODO (Member B): implement real conflict detection.
    """
    directions = [
        e["result"].get("direction")
        for e in evidence
        if isinstance(e.get("result"), dict)
    ]
    return "positive" in directions and "negative" in directions


def run_agent(question: str, user_profile: dict | None = None) -> dict:
    """
    Main entry point. Runs the full Perceive → Decide → Act → Loop cycle.

    Args:
        question: the user's natural-language question
        user_profile: optional dict with budget, timeframe, risk_comfort

    Returns:
        A report dict with keys: summary, opportunities, risks, evidence, confidence
    """

    # ── PERCEIVE ──────────────────────────────────────────────────────
    plan = llm_plan(question)
    evidence = []   # accumulates (action, result) pairs

    # ── LOOP ──────────────────────────────────────────────────────────
    for step in range(MAX_STEPS):

        # ── DECIDE ────────────────────────────────────────────────────
        action = llm_decide(plan, evidence)

        if action["type"] == "ask_user":
            # Return immediately — the UI will re-call run_agent with the answer
            return {"type": "ask_user", "question": action["question"]}

        if action["type"] == "finish":
            break

        # ── ACT ───────────────────────────────────────────────────────
        tool_fn = TOOLS.get(action["tool"])
        if tool_fn is None:
            break   # unknown tool — stop safely

        result = tool_fn(**action["args"])
        evidence.append({"action": action, "result": result})

        # ── CHECK FOR CONFLICT ────────────────────────────────────────
        if has_conflict(evidence):
            # Lower confidence for conflicting evidence; search again
            plan["conflict_detected"] = True

    # ── WRITE REPORT ─────────────────────────────────────────────────
    report = write_report(question=question, evidence=evidence, plan=plan)
    return report


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    question = "I want to open a small cafe in Kandy. Is it a good idea now?"
    report = run_agent(question)
    print("=== AGENT REPORT ===")
    print(report)
