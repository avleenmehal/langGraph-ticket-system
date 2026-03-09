import os
import json
import requests
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt
from graph.TriageState import TriageState

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
REFUND_TYPES = {"duplicate_charge", "refund_request", "late_delivery", "missing_item"}


def _get_llm():
    """Lazy init so OPENAI_API_KEY is read after load_dotenv runs."""
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


def propose_remedy_node(state: TriageState) -> TriageState:
    """
    1. Calls payments.refund_preview (or replacement_preview) to get proposed action.
    2. Calls LLM to generate a structured recommendation for the admin.
    3. Interrupts for human approval — preview passed via interrupt payload.
    4. On resume: calls payments.refund_commit (or replacement_commit).

    NOTE: state mutations before interrupt() are NOT checkpointed (LangGraph behaviour).
    The enriched preview is passed through the interrupt payload so the API can read it
    from graph_state.tasks[*].interrupts[*].value without relying on committed state.
    After resume the node returns normally, so all state updates ARE checkpointed.
    """
    issue_type = state.get("issue_type")
    order_id = state.get("order_id")
    citations = state.get("policy_citations", [])

    # --- Step 1: Call payments.refund_preview / replacement_preview ---
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

    # --- Step 2: LLM recommendation for admin ---
    order = state.get("evidence", {})
    ticket = state.get("ticket_text", "")
    policy_evidence = state.get("policy_evidence", [])

    policy_text = "\n\n".join(
        f"[{p['file']}] (similarity={p['similarity']}):\n{p['text']}"
        for p in policy_evidence
    ) if policy_evidence else "No policy chunks retrieved."

    system_prompt = """You are a customer support triage assistant for the company Viridien.
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

    try:
        response = _get_llm().invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        llm_recommendation = response.content
    except Exception as e:
        llm_recommendation = f"LLM unavailable: {e}"

    enriched_preview = {
        **raw_preview,
        "llm_recommendation": llm_recommendation,
        "policy_citations": citations,
        "order": order,   # full order details for admin review
    }

    # --- Step 3: Interrupt — preview passed in payload so API can read it ---
    # graph_state.tasks[*].interrupts[*].value holds this dict after invoke() pauses.
    approved = interrupt({
        "preview": enriched_preview,
        "policy_citations": citations,
        "issue_type": issue_type,
        "message": "Review the remedy preview. Approve or reject.",
    })

    # --- Step 4: Resume — commit the approved action ---
    # Node now returns normally → all state updates below ARE checkpointed.
    state["refund_preview"] = enriched_preview
    state["approval_status"] = "approved" if approved else "rejected"

    if not approved:
        state["final_status"] = "rejected"
        state["recommendation"] = "Remedy rejected by admin. No action taken."
        state["messages"].append({"role": "system", "content": "Admin rejected the remedy."})
        return state

    # Call payments.refund_commit / replacement_commit
    if issue_type in REFUND_TYPES:
        amount = enriched_preview.get("refund_amount", 0)
        commit_resp = requests.post(
            f"{BACKEND_URL}/refund/commit",
            json={"order_id": order_id, "amount": amount, "issue_type": issue_type}
        )
    else:
        commit_resp = requests.post(
            f"{BACKEND_URL}/replacement/commit",
            json={"order_id": order_id, "issue_type": issue_type}
        )

    commit_result = commit_resp.json() if commit_resp.ok else {"error": "Commit failed"}
    state["final_status"] = commit_result.get("status", "unknown")
    state["messages"].append({
        "role": "system",
        "content": f"Action committed: {state['final_status']}"
    })

    return state
