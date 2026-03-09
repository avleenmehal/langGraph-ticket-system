"""
kb_orchestrator node.

Sits between classify and generate_preview in the main graph.
Invokes the RAG subgraph to retrieve relevant policy chunks, then writes:
  - policy_citations: list of filenames (for display / admin)
  - policy_evidence:  full text of retrieved chunks (for LLM reasoning)
"""

from graph.TriageState import TriageState
from graph.rag_subgraph import rag_subgraph


def kb_orchestrator_node(state: TriageState) -> TriageState:
    rag_input = {
        "ticket_text": state.get("ticket_text", ""),
        "issue_type": state.get("issue_type", ""),
        "query": "",
        "raw_results": [],
        "citations": [],
        "retry_count": 0,
        "sufficient": False,
    }

    rag_result = rag_subgraph.invoke(rag_input)
    citations = rag_result.get("citations", [])

    # Filenames for display in the admin interrupt payload
    state["policy_citations"] = list({c["file"] for c in citations})

    # Full text for the LLM to reason over in generate_preview
    state["policy_evidence"] = [
        {"file": c["file"], "text": c["text"], "similarity": c["similarity"]}
        for c in citations
    ]

    state["messages"].append({
        "role": "assistant",
        "content": (
            f"Policy citations retrieved: {state['policy_citations']} "
            f"(sufficient={rag_result.get('sufficient')}, "
            f"retries={rag_result.get('retry_count')})"
        )
    })

    return state
