from __future__ import annotations

from typing import TypedDict


class TriageState(TypedDict):
    messages: list
    ticket_text: str
    order_id: str | None
    customer_email: str | None
    issue_type: str | None
    evidence: dict | None
    recommendation: str | None
    policy_citations: list | None       # filenames e.g. ["refund_policy.md"]
    policy_evidence: list | None        # full text chunks for LLM reasoning
    refund_preview: dict | None         # enriched preview (amounts, item, LLM recommendation)
    approval_status: str | None         # "approved" | "rejected"
    final_status: str | None            # "refund_committed" | "replacement_authorized"
    # --- Evaluator agent outputs (written back from evaluator subgraph) ---
    eval_risk_tier: str | None          # "normal" | "watch" | "flagged"
    eval_ticket_count: int | None       # total historical tickets for this customer
    eval_confidence_decision: str | None  # "auto_approve" | "escalate" | "auto_reject"
    eval_reasoning: str | None          # LLM explanation of the confidence decision
