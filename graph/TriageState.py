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
    email_mismatch: bool | None
