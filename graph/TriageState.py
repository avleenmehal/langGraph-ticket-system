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
    refund_preview: dict | None         # raw preview (amounts, item) + LLM recommendation
    approval_status: str | None         # "approved" | "rejected"
    final_status: str | None            # "refund_committed" | "replacement_authorized"
