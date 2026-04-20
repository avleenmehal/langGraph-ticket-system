"""
Evaluator Agent Subgraph

Checks the customer's historical claim behaviour and the confidence.md policy
before allowing a remedy to proceed. The interrupt() lives here — not in propose_remedy.

Internal state: EvaluatorState
Nodes:
  update_risk_tier    — queries support_tickets DB, recalculates and persists customer risk_tier
  evaluate_confidence — reads confidence.md, calls LLM → auto_approve | escalate | auto_reject
  human_review        — interrupt node, only reached on 'escalate'; awaits admin decision

Flow:
  update_risk_tier → evaluate_confidence
                            │
              auto_approve ──→ END  (approval_status = 'approved')
              auto_reject  ──→ END  (approval_status = 'rejected')
              escalate     ──→ human_review → END

NOTE: This subgraph is compiled WITHOUT its own checkpointer so that interrupt() bubbles
up to the parent graph's PostgreSQL checkpointer. Add it to the parent graph as a node:
    graph.add_node("evaluator_agent", build_evaluator_subgraph())

Set POLICY_DIR in graph/.env to the directory containing confidence.md, e.g.:
    POLICY_DIR=/path/to/p2-umber-abbey-main/mock_data/policies
"""

import os
import re
import json
import psycopg
from typing import TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/viridien")
# POLICY_DIR is intentionally NOT read here — it must be read inside the node function
# so that load_dotenv() in main.py has already run before os.getenv is called.


# ---------- Internal state ----------

class EvaluatorState(TypedDict):
    # Shared with TriageState — automatically mapped in/out by LangGraph
    customer_email: str | None
    order_id: str | None
    issue_type: str | None
    refund_preview: dict | None
    policy_citations: list | None
    approval_status: str | None
    eval_risk_tier: str | None
    eval_ticket_count: int | None
    eval_confidence_decision: str | None
    eval_reasoning: str | None
    # Internal computation — not synced back to TriageState
    recent_ticket_count: int | None
    total_claimed_amount: float | None


# ---------- Node 1: update_risk_tier ----------

def update_risk_tier_node(state: EvaluatorState) -> EvaluatorState:
    """
    Queries support_tickets for this customer, recalculates risk_tier,
    and updates the customers table in the DB.
    """
    email = state.get("customer_email")
    if not email:
        state["eval_risk_tier"] = "normal"
        state["eval_ticket_count"] = 0
        state["recent_ticket_count"] = 0
        state["total_claimed_amount"] = 0.0
        return state

    with psycopg.connect(DB_URL, autocommit=True) as conn:
        # Total tickets ever
        row = conn.execute(
            "SELECT COUNT(*) FROM support_tickets WHERE customer_email = %s",
            (email,)
        ).fetchone()
        ticket_count = int(row[0]) if row else 0

        # Tickets in last 90 days
        row = conn.execute(
            """SELECT COUNT(*) FROM support_tickets
               WHERE customer_email = %s
               AND requested_at > NOW() - INTERVAL '90 days'""",
            (email,)
        ).fetchone()
        recent_count = int(row[0]) if row else 0

        # Total approved refund amount (all time)
        row = conn.execute(
            """SELECT COALESCE(SUM((resolution->>'amount')::numeric), 0)
               FROM support_tickets
               WHERE customer_email = %s
               AND ticket_type = 'refund'
               AND outcome = 'approved'""",
            (email,)
        ).fetchone()
        total_claimed = float(row[0]) if row else 0.0

        # Recalculate risk tier
        if ticket_count >= 4:
            risk_tier = "flagged"
        elif ticket_count >= 2:
            risk_tier = "watch"
        else:
            risk_tier = "normal"

        # Persist updated risk tier
        conn.execute(
            "UPDATE customers SET risk_tier = %s WHERE email = %s",
            (risk_tier, email)
        )

    state["eval_risk_tier"] = risk_tier
    state["eval_ticket_count"] = ticket_count
    state["recent_ticket_count"] = recent_count
    state["total_claimed_amount"] = total_claimed
    return state


# ---------- Node 2: evaluate_confidence ----------

def evaluate_confidence_node(state: EvaluatorState) -> EvaluatorState:
    """
    Reads confidence.md and calls the LLM to decide:
    auto_approve | escalate | auto_reject.
    Sets approval_status for auto decisions so human_review is bypassed.
    """
    confidence_path = os.path.join(os.getenv("POLICY_DIR", ""), "confidence.md")
    try:
        with open(confidence_path) as f:
            confidence_policy = f.read()
    except FileNotFoundError:
        confidence_policy = (
            "Policy file not found. Escalate all tickets to human review as a safe default."
        )

    risk_signals = {
        "risk_tier": state.get("eval_risk_tier"),
        "total_ticket_count": state.get("eval_ticket_count"),
        "recent_ticket_count_90d": state.get("recent_ticket_count"),
        "total_approved_refund_amount_usd": state.get("total_claimed_amount"),
    }

    system_prompt = f"""You are a fraud risk evaluator for Viridien customer support.
Using the confidence policy below, evaluate whether this ticket should be
auto-approved, escalated to a human reviewer, or auto-rejected.

## Confidence Policy
{confidence_policy}"""

    human_prompt = f"""## Customer Risk Signals
{json.dumps(risk_signals, indent=2)}

## Issue Type
{state.get("issue_type")}

## Remedy Preview & LLM Recommendation
{json.dumps(state.get("refund_preview", {}), indent=2, default=str)}

## Policy Citations Retrieved
{state.get("policy_citations", [])}

Based on the policy, what is your decision? Respond with JSON only."""

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ])
        # Strip markdown fences if the LLM wraps the JSON in ```json ... ```
        content = response.content.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if fence_match:
            content = fence_match.group(1)
        result = json.loads(content)
        decision = result.get("decision", "escalate")
        reasoning = result.get("reasoning", "")
    except Exception as e:
        decision = "escalate"
        reasoning = f"Confidence evaluation failed ({e}); defaulting to human review."

    state["eval_confidence_decision"] = decision
    state["eval_reasoning"] = reasoning

    if decision == "auto_approve":
        state["approval_status"] = "approved"
    elif decision == "auto_reject":
        state["approval_status"] = "rejected"
    # 'escalate' leaves approval_status unset — human_review node sets it on resume

    return state


# ---------- Node 3: human_review ----------

def human_review_node(state: EvaluatorState) -> EvaluatorState:
    """
    Pauses execution and surfaces all evaluation context to the admin.
    Resumes when the admin calls POST /triage/approve with approved=true|false.
    """
    approved = interrupt({
        "preview": state.get("refund_preview", {}),
        "policy_citations": state.get("policy_citations", []),
        "issue_type": state.get("issue_type"),
        "eval_risk_tier": state.get("eval_risk_tier"),
        "eval_ticket_count": state.get("eval_ticket_count"),
        "eval_reasoning": state.get("eval_reasoning"),
        "message": "Evaluator escalated this ticket for human review. Approve or reject.",
    })

    state["approval_status"] = "approved" if approved else "rejected"
    return state


# ---------- Routing ----------

def route_after_confidence(state: EvaluatorState) -> str:
    decision = state.get("eval_confidence_decision", "escalate")
    if decision in ("auto_approve", "auto_reject"):
        return "end"
    return "human_review"


# ---------- Build ----------

def build_evaluator_subgraph():
    evaluator = StateGraph(EvaluatorState)

    evaluator.add_node("update_risk_tier", update_risk_tier_node)
    evaluator.add_node("evaluate_confidence", evaluate_confidence_node)
    evaluator.add_node("human_review", human_review_node)

    evaluator.set_entry_point("update_risk_tier")
    evaluator.add_edge("update_risk_tier", "evaluate_confidence")
    evaluator.add_conditional_edges(
        "evaluate_confidence",
        route_after_confidence,
        {"human_review": "human_review", "end": END}
    )
    evaluator.add_edge("human_review", END)

    # Compiled WITHOUT a checkpointer — inherits parent graph's PostgreSQL checkpointer
    return evaluator.compile()
