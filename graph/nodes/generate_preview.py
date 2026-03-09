import os
import json
import requests
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from graph.TriageState import TriageState

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
REFUND_TYPES = {"duplicate_charge", "refund_request", "late_delivery", "missing_item"}


def _get_llm():
    """Lazy init so OPENAI_API_KEY is read after load_dotenv runs."""
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


def generate_preview_node(state: TriageState) -> TriageState:
    """
    1. Fetches raw preview (amounts/item) from backend.
    2. Calls LLM with full context: ticket, order, issue_type, policy evidence.
    3. LLM generates structured recommendation for admin review.
    4. Stores enriched preview in state — committed before propose_remedy interrupts.
    """
    issue_type = state.get("issue_type")
    order_id = state.get("order_id")
    citations = state.get("policy_citations", [])

    # --- Step 1: Get raw preview numbers from backend ---
    if issue_type in REFUND_TYPES:
        resp = requests.post(
            f"{BACKEND_URL}/refund/preview",
            json={"order_id": order_id, "issue_type": issue_type, "citations": citations}
        )
    else:
        resp = requests.post(
            f"{BACKEND_URL}/replacement/preview",
            json={"order_id": order_id, "issue_type": issue_type, "citations": citations}
        )

    raw_preview = resp.json() if resp.ok else {"error": "Preview failed"}

    # --- Step 2: Build LLM context ---
    order = state.get("evidence", {})
    ticket = state.get("ticket_text", "")
    policy_evidence = state.get("policy_evidence", [])

    policy_text = "\n\n".join(
        f"[{p['file']}] (similarity={p['similarity']}):\n{p['text']}"
        for p in policy_evidence
    ) if policy_evidence else "No policy chunks retrieved."

    system_prompt = """You are a customer support triage assistant.
Your job is to analyse a support ticket and generate a structured recommendation
for an ADMIN to review and approve before any action is taken.

Be specific, cite the exact policy sections, and flag any risks."""

    human_prompt = f"""## Support Ticket
{ticket}

## Order Details
{json.dumps(order, indent=2, default=str)}

## Classified Issue
{issue_type}

## Proposed Action (from backend)
{json.dumps(raw_preview, indent=2, default=str)}

## Retrieved Policy Sections
{policy_text}

---
Generate a structured admin recommendation with these exact sections:

**RECOMMENDED ACTION**: (one sentence, specific — e.g. "Issue full refund of $120.50")
**POLICY JUSTIFICATION**: (cite the specific policy file and rule that authorises this)
**RISK ASSESSMENT**: low / medium / high — and why
**CUSTOMER REPLY**: (the message to send to the customer if admin approves)
"""

    # --- Step 3: Call LLM ---
    try:
        response = _get_llm().invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        llm_recommendation = response.content
    except Exception as e:
        llm_recommendation = f"LLM unavailable: {e}"

    # --- Step 4: Enrich preview with LLM output and commit state ---
    enriched_preview = {
        **raw_preview,
        "llm_recommendation": llm_recommendation,
        "policy_citations": citations,
    }

    state["refund_preview"] = enriched_preview
    state["messages"].append({
        "role": "assistant",
        "content": f"LLM recommendation generated for {issue_type}"
    })

    return state
