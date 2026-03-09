import os
import psycopg
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from graph.TriageState import TriageState
from graph.nodes.ingest import ingest_node
from graph.nodes.classify import classify_node
from graph.nodes.fetch_order import fetch_order_node
from graph.nodes.draft_reply import draft_reply_node
from graph.nodes.no_order_id import no_order_id_node
from graph.nodes.search_orders import search_orders_node
from graph.nodes.kb_orchestrator import kb_orchestrator_node
from graph.nodes.propose_remedy import propose_remedy_node

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/viridien")


def route_after_ingest(state: TriageState) -> str:
    if state.get("order_id"):
        return "fetch_order"
    elif state.get("customer_email"):
        return "search_orders"
    else:
        return "no_order_id"


def route_after_search(state: TriageState) -> str:
    if state.get("order_id"):
        return "classify"
    else:
        return "no_order_id"


def route_after_approval(state: TriageState) -> str:
    if state.get("approval_status") == "approved":
        return "draft_reply"
    return "end"


def build_graph():
    graph_agent = StateGraph(TriageState)

    # --- Nodes ---
    graph_agent.add_node("ingest", ingest_node)
    graph_agent.add_node("fetch_order", fetch_order_node)
    graph_agent.add_node("search_orders", search_orders_node)
    graph_agent.add_node("classify", classify_node)
    graph_agent.add_node("kb_orchestrator", kb_orchestrator_node)
    graph_agent.add_node("propose_remedy", propose_remedy_node)
    graph_agent.add_node("draft_reply", draft_reply_node)
    graph_agent.add_node("no_order_id", no_order_id_node)

    # --- Entry ---
    graph_agent.set_entry_point("ingest")

    # --- Conditional: after ingest ---
    graph_agent.add_conditional_edges(
        "ingest",
        route_after_ingest,
        {"fetch_order": "fetch_order", "search_orders": "search_orders", "no_order_id": "no_order_id"}
    )

    # --- Conditional: after search_orders ---
    graph_agent.add_conditional_edges(
        "search_orders",
        route_after_search,
        {"classify": "classify", "no_order_id": "no_order_id"}
    )

    # --- Happy path ---
    # fetch_order → classify → kb_orchestrator → propose_remedy
    # propose_remedy: calls refund_preview, calls LLM, interrupts for admin, on resume calls refund_commit
    graph_agent.add_edge("fetch_order", "classify")
    graph_agent.add_edge("classify", "kb_orchestrator")
    graph_agent.add_edge("kb_orchestrator", "propose_remedy")

    # --- Conditional: after propose_remedy (post-interrupt resume) ---
    graph_agent.add_conditional_edges(
        "propose_remedy",
        route_after_approval,
        {"draft_reply": "draft_reply", "end": END}
    )

    graph_agent.add_edge("draft_reply", END)
    graph_agent.add_edge("no_order_id", END)

    # --- Postgres checkpointer ---
    conn = psycopg.connect(DB_URL, autocommit=True)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()

    return graph_agent.compile(checkpointer=checkpointer)
