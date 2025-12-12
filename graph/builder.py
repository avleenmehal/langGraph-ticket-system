from langgraph.graph import StateGraph, END

from graph.TriageState import TriageState
from graph.nodes.ingest import ingest_node
from graph.nodes.classify import classify_node
from graph.nodes.fetch_order import fetch_order_node
from graph.nodes.draft_reply import draft_reply_node
from graph.nodes.no_order_id import no_order_id_node
from graph.nodes.search_orders import search_orders_node


def route_after_ingest(state: TriageState) -> str:
    """
    Route after ingest based on whether order_id or customer_email was extracted.
    Priority: order_id > customer_email > no_order_id
    """
    if state.get("order_id"):
        return "fetch_order"
    elif state.get("customer_email"):
        return "search_orders"
    else:
        return "no_order_id"


def route_after_search(state: TriageState) -> str:
    """
    Route after order search based on whether an order_id was found.
    If order found, continue to fetch_order. Otherwise, end workflow.
    """
    if state.get("order_id"):
        return "classify"
    else:
        return "no_order_id"


def build_graph():
    """
    Builds and compiles the triage workflow graph.
    """
    graph_agent = StateGraph(TriageState)

    # ADDING NODES
    graph_agent.add_node("ingest", ingest_node)
    graph_agent.add_node("classify", classify_node)
    graph_agent.add_node("fetch_order", fetch_order_node)
    graph_agent.add_node("draft_reply", draft_reply_node)
    graph_agent.add_node("no_order_id", no_order_id_node)
    graph_agent.add_node("search_orders", search_orders_node)

    # DEFINING EDGES (workflow flow)
    graph_agent.set_entry_point("ingest")

    # Conditional edge after ingest
    graph_agent.add_conditional_edges(
        "ingest",
        route_after_ingest,
        {
            "fetch_order": "fetch_order",
            "search_orders": "search_orders",
            "no_order_id": "no_order_id"
        }
    )

    # Conditional edge after search_orders
    graph_agent.add_conditional_edges(
        "search_orders",
        route_after_search,
        {
            "classify": "classify",
            "no_order_id": "no_order_id"
        }
    )

    # Normal workflow: fetch_order -> classify -> draft_reply
    graph_agent.add_edge("fetch_order", "classify")
    graph_agent.add_edge("classify", "draft_reply")
    graph_agent.add_edge("draft_reply", END)

    # Error path when no order_id
    graph_agent.add_edge("no_order_id", END)

    # Compile and return the graph
    return graph_agent.compile()