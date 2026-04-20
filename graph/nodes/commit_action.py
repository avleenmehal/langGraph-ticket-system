import os
import requests
from graph.TriageState import TriageState

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
REFUND_TYPES = {"duplicate_charge", "refund_request", "late_delivery", "missing_item"}


def commit_action_node(state: TriageState) -> TriageState:
    """
    Runs after evaluator_agent approves the remedy.
    Calls refund/commit or replacement/commit on the backend and records final_status.
    """
    issue_type = state.get("issue_type")
    order_id = state.get("order_id")
    enriched_preview = state.get("refund_preview", {})

    if issue_type in REFUND_TYPES:
        amount = enriched_preview.get("refund_amount", 0)
        resp = requests.post(
            f"{BACKEND_URL}/refund/commit",
            json={"order_id": order_id, "amount": amount, "issue_type": issue_type}
        )
    else:
        resp = requests.post(
            f"{BACKEND_URL}/replacement/commit",
            json={"order_id": order_id, "issue_type": issue_type}
        )

    commit_result = resp.json() if resp.ok else {"error": "Commit failed"}
    state["final_status"] = commit_result.get("status", "unknown")
    state["messages"].append({
        "role": "system",
        "content": f"Action committed: {state['final_status']}"
    })
    return state
