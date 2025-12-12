from graph.TriageState import TriageState


def no_order_id_node(state: TriageState) -> TriageState:
    """
    Node that handles cases where no order_id was found.
    Sets an error message in the recommendation field.
    """
    state["recommendation"] = "We cannot proceed with the issue. Please provide Order ID in the ticket. "
    state["messages"].append({"role": "system", "content": "Workflow stopped: missing order_id"})
    return state
