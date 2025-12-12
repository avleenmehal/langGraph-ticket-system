import os
import requests

from graph.TriageState import TriageState


def classify_node(state: TriageState) -> TriageState:
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    endpoint = f"{backend_url}/classify/issue"

    payload = {
        "ticket_text": state["ticket_text"]
    }

    try:
        response = requests.post(endpoint, json=payload)
        response.raise_for_status()
        result = response.json()

        # Updating state with classified issue type
        state["issue_type"] = result.get("issue_type")
        state["messages"].append({"role": "assistant", "content": f"Classified as: {state['issue_type']}"})

        return state

    except requests.exceptions.RequestException as e:
        print(f"Error calling classify endpoint: {e}")
        state["issue_type"] = "unknown"
        state["messages"].append({"role": "assistant", "content": "Classification failed, set to unknown"})
        return state
