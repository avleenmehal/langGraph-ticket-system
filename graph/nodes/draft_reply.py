import os
import requests

from graph.TriageState import TriageState


def draft_reply_node(state: TriageState) -> TriageState:
    """
    Node that calls the backend reply/draft endpoint to generate a response.
    """
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    endpoint = f"{backend_url}/reply/draft"

    payload = {
        "issue_type": state.get("issue_type"),
        "order": state.get("evidence", {})
    }

    try:
        response = requests.post(endpoint, json=payload)
        response.raise_for_status()
        result = response.json()

        # Update state with drafted reply
        state["recommendation"] = result.get("reply_text")
        state["messages"].append({"role": "assistant", "content": "Generated reply recommendation"})

        return state

    except requests.exceptions.RequestException as e:
        print(f"Error calling reply/draft endpoint: {e}")
        state["recommendation"] = "Unable to generate response at this time."
        state["messages"].append({"role": "assistant", "content": "Failed to generate reply"})
        return state
