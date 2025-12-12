from graph.TriageState import TriageState


def email_mismatch_node(state: TriageState) -> TriageState:
    """
    Node that handles email mismatch scenarios.
    Sets a recommendation indicating the order and email do not match.
    """
    extracted_email = state.get("customer_email", "unknown")
    order_email = state.get("evidence", {}).get("customer_email", "unknown")

    state["recommendation"] = (
        f"Your order and email do not match. "
        f"The email '{extracted_email}' from your ticket does not match "
        f"the email '{order_email}' associated with this order. "
        f"Please verify your order ID and email address."
    )

    state["messages"].append({
        "role": "assistant",
        "content": "Email validation failed - ending workflow"
    })

    return state
