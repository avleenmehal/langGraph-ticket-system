import os
import requests
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from graph.TriageState import TriageState


@tool
def fetch_order_tool(order_id: str) -> dict:
    """
    Fetches order details from the backend API.

    Args:
        order_id: The order ID to fetch details for

    Returns:
        dict: Order details or error information
    """
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    endpoint = f"{backend_url}/orders/get"

    try:
        response = requests.get(endpoint, params={"order_id": order_id})
        response.raise_for_status()
        order_data = response.json()
        return order_data

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return {"error": "Order not found"}
        else:
            return {"error": f"HTTP error: {str(e)}"}

    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}


def fetch_order_node(state: TriageState) -> TriageState:
    """
    Node that uses the fetch_order tool to get order details.
    """
    order_id = state.get("order_id")

    if not order_id:
        print("No order_id found in state, skipping order fetch")
        state["messages"].append({"role": "assistant", "content": "Skipped order fetch: no order_id"})
        return state

    # Call the tool
    result = fetch_order_tool.invoke({"order_id": order_id})

    if "error" in result:
        state["evidence"] = result
        state["messages"].append({"role": "assistant", "content": f"Error: {result['error']}"})
    else:
        state["evidence"] = result
        state["messages"].append({"role": "assistant", "content": f"Fetched order details: {order_id}"})

    return state


# Create ToolNode for use in graph
fetch_order_tool_node = ToolNode([fetch_order_tool])
