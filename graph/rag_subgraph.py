"""
Agentic RAG subgraph.

Internal state: RAGState
Nodes:
  build_query       — constructs search query from ticket_text + issue_type
  retrieve          — pgvector top-k similarity search via /kb/search
  grade_and_select  — filters by similarity threshold; increments retry on failure

Flow:
  build_query → retrieve → grade_and_select
                                  │
                      sufficient? → YES → END (citations ready)
                                  → NO  → build_query (reformulate, max 2 retries)
"""

import os
import requests
from typing import TypedDict
from langgraph.graph import StateGraph, END

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
SIMILARITY_THRESHOLD = 0.25   # minimum score to consider a chunk relevant
MAX_RETRIES = 2


# ---------- RAG-specific state (internal to subgraph) ----------

class RAGState(TypedDict):
    ticket_text: str
    issue_type: str
    query: str                  # constructed search query
    raw_results: list           # full results from /kb/search
    citations: list             # filtered list of {"file", "text", "similarity"}
    retry_count: int
    sufficient: bool


# ---------- Nodes ----------

def build_query_node(state: RAGState) -> RAGState:
    """
    Constructs the search query.
    First pass: combines ticket_text + issue_type.
    Retries: falls back to issue_type keyword only (broader match).
    """
    if state["retry_count"] == 0:
        # First attempt: full context
        state["query"] = f"{state['ticket_text']} {state['issue_type']}".strip()
    else:
        # Retry: issue_type only — broader, less noisy
        state["query"] = state["issue_type"].replace("_", " ")

    return state


def retrieve_node(state: RAGState) -> RAGState:
    """Calls /kb/search with the current query. Stores raw results."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/kb/search",
            json={"query": state["query"], "top_k": 3},
            timeout=5
        )
        response.raise_for_status()
        state["raw_results"] = response.json().get("results", [])
    except requests.RequestException:
        state["raw_results"] = []

    return state


def grade_and_select_node(state: RAGState) -> RAGState:
    """
    Filters results by similarity threshold.
    If enough relevant chunks found → sufficient = True.
    Otherwise increments retry_count for reformulation.
    """
    relevant = [
        {"file": r["file"], "text": r["text"], "similarity": r["similarity"]}
        for r in state["raw_results"]
        if r["similarity"] >= SIMILARITY_THRESHOLD
    ]

    if relevant:
        state["citations"] = relevant
        state["sufficient"] = True
    else:
        # Not sufficient — keep any results we got as fallback
        state["citations"] = state["raw_results"][:2]
        state["sufficient"] = False
        state["retry_count"] = state["retry_count"] + 1

    return state


# ---------- Routing ----------

def route_after_grade(state: RAGState) -> str:
    """Retry if not sufficient and retries remain, otherwise end."""
    if state["sufficient"] or state["retry_count"] >= MAX_RETRIES:
        return END
    return "build_query"


# ---------- Build + compile the subgraph ----------

def build_rag_subgraph():
    rag = StateGraph(RAGState)

    rag.add_node("build_query", build_query_node)
    rag.add_node("retrieve", retrieve_node)
    rag.add_node("grade_and_select", grade_and_select_node)

    rag.set_entry_point("build_query")
    rag.add_edge("build_query", "retrieve")
    rag.add_edge("retrieve", "grade_and_select")

    rag.add_conditional_edges(
        "grade_and_select",
        route_after_grade,
        {"build_query": "build_query", END: END}
    )

    return rag.compile()


# Compile once at import time — reused across all requests

rag_subgraph = build_rag_subgraph()
