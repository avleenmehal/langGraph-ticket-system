import os
import uuid
import json
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langgraph.types import Command

from app.TriageInput import TriageInput
from graph.builder import build_graph

load_dotenv("graph/.env")

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/viridien")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Graph built once at startup
triage_graph = build_graph()


# ---------- Models ----------

class ApproveInput(BaseModel):
    thread_id: str
    approved: bool


# ---------- DB helpers ----------

def db():
    return psycopg.connect(DB_URL, autocommit=True)

def insert_session(thread_id, ticket_text, order_id):
    with db() as conn:
        conn.execute(
            "INSERT INTO triage_sessions (thread_id, ticket_text, order_id) VALUES (%s, %s, %s)",
            (thread_id, ticket_text, order_id)
        )

def update_session_preview(thread_id, issue_type, policy_citations, preview):
    with db() as conn:
        conn.execute(
            """UPDATE triage_sessions
               SET issue_type=%s, policy_citations=%s, preview=%s, updated_at=NOW()
               WHERE thread_id=%s""",
            (issue_type, policy_citations, json.dumps(preview), thread_id)
        )

def update_session_result(thread_id, status, final_result):
    with db() as conn:
        conn.execute(
            """UPDATE triage_sessions
               SET status=%s, final_result=%s, updated_at=NOW()
               WHERE thread_id=%s""",
            (status, json.dumps(final_result), thread_id)
        )


# ---------- Serve UI ----------

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def root():
    return FileResponse("app/static/index.html")


# ---------- Health ----------

@app.get("/triage")
async def triage():
    return {"status": "triage service is running"}


# ---------- Customer: submit ticket ----------

@app.post("/triage/invoke")
async def invoke(body: TriageInput):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "ticket_text": body.ticket_text,
        "order_id": body.order_id,
        "messages": [],
        "issue_type": None,
        "customer_email": None,
        "evidence": None,
        "recommendation": None,
        "policy_citations": None,
        "policy_evidence": None,
        "refund_preview": None,
        "approval_status": None,
        "final_status": None,
        "eval_risk_tier": None,
        "eval_ticket_count": None,
        "eval_confidence_decision": None,
        "eval_reasoning": None,
    }

    insert_session(thread_id, body.ticket_text, body.order_id)
    result = triage_graph.invoke(initial_state, config=config)
    graph_state = triage_graph.get_state(config)

    if graph_state.next:
        # state mutations inside propose_remedy before interrupt() are not checkpointed —
        # read the enriched preview from the interrupt payload instead.
        interrupt_payload = {}
        for task in graph_state.tasks:
            for intr in getattr(task, "interrupts", []):
                interrupt_payload = intr.value
                break
            if interrupt_payload:
                break

        preview = interrupt_payload.get("preview", {})
        committed = graph_state.values  # contains issue_type, policy_citations from prior nodes

        update_session_preview(
            thread_id,
            committed.get("issue_type"),
            committed.get("policy_citations"),
            preview,
        )
        return {
            "status": "pending_approval",
            "thread_id": thread_id,
            "issue_type": committed.get("issue_type"),
            "order_id": committed.get("order_id"),
            "preview": preview,
            "policy_citations": committed.get("policy_citations"),
            "eval_risk_tier": committed.get("eval_risk_tier"),
            "eval_ticket_count": committed.get("eval_ticket_count"),
            "eval_confidence_decision": committed.get("eval_confidence_decision"),
            "eval_reasoning": committed.get("eval_reasoning"),
        }

    # No interrupt — check for auto evaluation decisions or terminal paths (no_order_id)
    eval_decision = result.get("eval_confidence_decision")

    if eval_decision == "auto_reject":
        update_session_result(thread_id, "auto_rejected", result)
        return {
            "status": "auto_rejected",
            "thread_id": thread_id,
            "eval_risk_tier": result.get("eval_risk_tier"),
            "eval_ticket_count": result.get("eval_ticket_count"),
            "eval_reasoning": result.get("eval_reasoning"),
        }

    if eval_decision == "auto_approve":
        update_session_result(thread_id, "completed", result)
        return {**result, "status": "completed"}

    update_session_result(thread_id, "completed", result)
    return result


# ---------- Admin: approve or reject ----------

@app.post("/triage/approve")
async def approve(body: ApproveInput):
    config = {"configurable": {"thread_id": body.thread_id}}

    graph_state = triage_graph.get_state(config)
    if not graph_state.next:
        raise HTTPException(status_code=404, detail="No pending approval for this thread_id")

    result = triage_graph.invoke(Command(resume=body.approved), config=config)

    status = "approved" if body.approved else "rejected"
    update_session_result(body.thread_id, status, result)
    return result


# ---------- Admin: list sessions ----------

@app.get("/triage/sessions")
async def list_sessions(status: str = None):
    with db() as conn:
        if status:
            rows = conn.execute(
                "SELECT thread_id, ticket_text, order_id, issue_type, policy_citations, "
                "preview, status, final_result, created_at "
                "FROM triage_sessions WHERE status=%s ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT thread_id, ticket_text, order_id, issue_type, policy_citations, "
                "preview, status, final_result, created_at "
                "FROM triage_sessions ORDER BY created_at DESC LIMIT 20"
            ).fetchall()

    cols = ["thread_id", "ticket_text", "order_id", "issue_type",
            "policy_citations", "preview", "status", "final_result", "created_at"]
    return {"sessions": [dict(zip(cols, r)) for r in rows]}


# ---------- Customer: poll status ----------

@app.get("/triage/status/{thread_id}")
async def get_status(thread_id: str):
    with db() as conn:
        row = conn.execute(
            "SELECT thread_id, ticket_text, order_id, issue_type, policy_citations, "
            "preview, status, final_result, created_at "
            "FROM triage_sessions WHERE thread_id=%s",
            (thread_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    cols = ["thread_id", "ticket_text", "order_id", "issue_type",
            "policy_citations", "preview", "status", "final_result", "created_at"]
    return dict(zip(cols, row))
