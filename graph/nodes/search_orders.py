import os
import requests
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from graph.TriageState import TriageState


@tool
def search_orders_tool(customer_email: str = None, query: str = None) -> dict:
    """
    Searches for orders using customer email or query string.

    Args:
        customer_email: Customer email to search for
        query: Query string to search in order_id or customer_name

    Returns:
        dict: Search results with list of matching orders
    """
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    endpoint = f"{backend_url}/orders/search"

    params = {}
    if customer_email:
        params["customer_email"] = customer_email
    if query:
        params["q"] = query

    try:
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        return {"error": f"Search failed: {str(e)}", "results": []}


def search_orders_node(state: TriageState) -> TriageState:
    """
    Node that uses the search_orders tool to find orders by customer email.
    """
    customer_email = state.get("customer_email")

    if not customer_email:
        print("No customer_email found in state, cannot search orders")
        state["messages"].append({"role": "assistant", "content": "No customer email found for order search"})
        return state

    # Call the tool
    result = search_orders_tool.invoke({"customer_email": customer_email})

    if "error" in result:
        state["messages"].append({"role": "assistant", "content": f"Error: {result['error']}"})
        return state

    results = result.get("results", [])

    if len(results) == 0:
        state["messages"].append({"role": "assistant", "content": f"No orders found for email: {customer_email}"})
    elif len(results) == 1:
        # Single match - use this order
        order = results[0]
        state["order_id"] = order.get("order_id")
        state["evidence"] = order
        state["messages"].append({"role": "assistant", "content": f"Found order {state['order_id']} for email {customer_email}"})
    else:
        # Multiple matches - store all in evidence
        state["evidence"] = {"multiple_orders": results, "count": len(results)}
        state["messages"].append({"role": "assistant", "content": f"Found {len(results)} orders for email {customer_email}"})

    return state


# Create ToolNode for use in graph
search_orders_tool_node = ToolNode([search_orders_tool])
