import re

from graph.TriageState import TriageState


def ingest_node(state: TriageState) -> TriageState:
    ticket_text = state["ticket_text"]

    state["messages"] = [
        {"role": "user", "content": ticket_text}
    ]

    # If order_id is not already in state, try to extract it from ticket_text
    if not state.get("order_id"):
        order_id = extract_order_id(ticket_text)
        if order_id:
            state["order_id"] = order_id
            state["messages"].append({"role": "assistant", "content": f"Extracted order_id: {order_id}"})
        else:
            state["messages"].append({"role": "assistant", "content": "No order_id found in ticket"})

            # Only extract email if order_id is not found
            if not state.get("customer_email"):
                customer_email = extract_email(ticket_text)
                if customer_email:
                    state["customer_email"] = customer_email
                    state["messages"].append({"role": "assistant", "content": f"Extracted email: {customer_email}"})
    else:
        state["messages"].append({"role": "assistant", "content": f"Order_id provided: {state['order_id']}"})

    return state


def extract_order_id(text: str) -> str | None:
    """
    Extracts order_id from ticket text using regex pattern.
    Matches format: ORD followed by exactly 4 digits (e.g., ORD1002, ORD1004)
    """
    print("Extracting order ID from text...")
    match = re.search(r"(ORD\d{4})", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def extract_email(text: str) -> str | None:
    """
    Extracts email address from ticket text using regex pattern.
    """
    print("Extracting email from text...")
    # Standard email pattern
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    match = re.search(email_pattern, text)
    if match:
        return match.group(0)

    return None
