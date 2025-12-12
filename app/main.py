from fastapi import FastAPI

from app.TriageInput import TriageInput
from graph.builder import build_graph

app = FastAPI()

# Build the graph once at startup
triage_graph = build_graph()

@app.get("/triage")
async def triage():
    """
    Simple endpoint to verify the triage service is running.
    """
    return {"status": "triage service is running"}

@app.post("/triage/invoke")
async def invoke(body: TriageInput):
    """
    Invoke the triage workflow with the provided ticket.
    """
    initial_state = {
        "ticket_text": body.ticket_text,
        "order_id": body.order_id,
        "messages": [],
        "issue_type": None,
        "evidence": None,
        "recommendation": None
    }

    result = triage_graph.invoke(initial_state)
    return result
