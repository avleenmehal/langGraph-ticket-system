# Viridien LangGraph Triage Agent (Phase 2)

A LangGraph multi-agent system that triages customer support tickets end-to-end: classifies the issue, retrieves relevant policy via an agentic RAG subgraph, generates an LLM-backed recommendation, and pauses for human admin approval before committing any action.

Persistence is handled by a PostgreSQL checkpointer — the graph can be stopped mid-run and resumed from the same thread after a restart.

## Prerequisites

- Python 3.12+
- PostgreSQL 17+ with the `pgvector` extension
- The Phase 2 backend (`p2-umber-abbey-main`) running on port 8000
- An OpenAI API key (for the LLM recommendation step)
- A LangSmith API key (for tracing — optional but recommended)

## Setup

```bash
python3.12 -m venv myenv
source myenv/bin/activate
pip install -r requirements.txt
```

Create `graph/.env`:

```
BACKEND_URL=http://localhost:8000
OPENAI_API_KEY=sk-...

# LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=ticket-system
```

The `viridien` PostgreSQL database must exist. The LangGraph service creates its own checkpoint tables automatically on first run (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`).

A separate `triage_sessions` table is needed for the UI session tracking:

```sql
CREATE TABLE IF NOT EXISTS triage_sessions (
    thread_id    TEXT PRIMARY KEY,
    ticket_text  TEXT,
    order_id     TEXT,
    issue_type   TEXT,
    policy_citations TEXT[],
    preview      JSONB,
    status       TEXT DEFAULT 'pending',
    final_result JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
```

## Running

Start the Phase 2 backend first, then:

```bash
./run.sh
# or
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Open `http://localhost:8001/` for the two-tab UI (Customer + Admin).

## Graph Architecture

### Main graph

```
ingest → [route] → fetch_order → classify → kb_orchestrator → propose_remedy → [route] → draft_reply → END
              ↘ search_orders ↗                                                        ↘ END (rejected)
              ↘ no_order_id → END
```

| Node | File | Role |
|------|------|------|
| `ingest` | `nodes/ingest.py` | Extracts `order_id` (regex `ORD\d{4}`) or `customer_email` |
| `fetch_order` | `nodes/fetch_order.py` | `GET /orders/get` — fetches full order details |
| `search_orders` | `nodes/search_orders.py` | `GET /orders/search` — finds order by email when no ID |
| `classify` | `nodes/classify.py` | `POST /classify/issue` — determines issue type |
| `kb_orchestrator` | `nodes/kb_orchestrator.py` | Runs the RAG subgraph; writes `policy_citations` and `policy_evidence` to state |
| `propose_remedy` | `nodes/propose_remedy.py` | Calls `refund_preview`, calls LLM, **interrupts** for admin approval, on resume calls `refund_commit` |
| `draft_reply` | `nodes/draft_reply.py` | `POST /reply/draft` — generates final customer-facing reply |
| `no_order_id` | `nodes/no_order_id.py` | Terminal error node |

### Agentic RAG subgraph (`graph/rag_subgraph.py`)

```
build_query → retrieve → grade_and_select → END (sufficient)
                  ↑____________↓ (retry, max 2)
```

- **`build_query`**: first pass uses full ticket text + issue type; retries use issue type only (broader match)
- **`retrieve`**: `POST /kb/search` — pgvector cosine similarity, top-3 chunks
- **`grade_and_select`**: filters by `similarity ≥ 0.25`; retries if no chunk clears the threshold

Embeddings are 384-dim (`all-MiniLM-L6-v2`), stored in pgvector on the backend.

### Human-in-the-loop (`propose_remedy`)

`propose_remedy` is the approval gate:

1. Calls `POST /refund/preview` (or `/replacement/preview`) for the proposed action
2. Calls GPT-4o-mini with the ticket, order details, and retrieved policy chunks — generates a structured recommendation (action, policy justification, risk level, draft customer reply)
3. Calls `interrupt({"preview": enriched_preview, ...})` — execution pauses, checkpoint saved to Postgres
4. Admin reviews via the UI and clicks Approve or Reject → `POST /triage/approve`
5. Graph resumes with `Command(resume=True/False)` — on approval calls `POST /refund/commit`

### Persistence

The graph is compiled with `PostgresSaver` (psycopg3):

```python
conn = psycopg.connect(DB_URL, autocommit=True)
checkpointer = PostgresSaver(conn)
checkpointer.setup()
graph = graph_agent.compile(checkpointer=checkpointer)
```

Each thread is identified by a `uuid4` thread ID. The checkpoint survives process restarts — a pending interrupt can be resumed after killing and restarting the server using the same `thread_id`.

**Demonstrated kill-and-resume:**
```bash
# 1. Submit a ticket → returns thread_id + status: pending_approval
curl -X POST http://localhost:8001/triage/invoke -d '{"ticket_text": "...", "order_id": "ORD1003"}'

# 2. Kill the server
kill -9 $(lsof -ti:8001)

# 3. Restart
uvicorn app.main:app --host 0.0.0.0 --port 8001

# 4. Resume — graph continues from the interrupt checkpoint
curl -X POST http://localhost:8001/triage/approve -d '{"thread_id": "<id>", "approved": true}'
# → final_status: refund_committed
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve the Customer/Admin UI |
| `GET` | `/triage` | Health check |
| `POST` | `/triage/invoke` | Submit a ticket; returns `pending_approval` + `thread_id` or final result |
| `POST` | `/triage/approve` | Admin approves or rejects a pending thread |
| `GET` | `/triage/sessions` | List all sessions (filterable by `?status=pending`) |
| `GET` | `/triage/status/{thread_id}` | Customer polls for result |

### Submit ticket

```bash
curl -X POST http://localhost:8001/triage/invoke \
  -H "Content-Type: application/json" \
  -d '{"ticket_text": "I was charged twice for order ORD1003.", "order_id": "ORD1003"}'
```

Response:
```json
{
  "status": "pending_approval",
  "thread_id": "uuid",
  "issue_type": "duplicate_charge",
  "preview": {
    "refund_amount": 120.50,
    "llm_recommendation": "**RECOMMENDED ACTION**: ...\n**POLICY JUSTIFICATION**: ...",
    "policy_citations": ["chargeback_policy.md", "refund_policy.md"]
  }
}
```

### Approve / reject

```bash
curl -X POST http://localhost:8001/triage/approve \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "uuid", "approved": true}'
```

## Observability

LangSmith traces every run. Navigate to [smith.langchain.com](https://smith.langchain.com) → project `ticket-system` to see:

- Full node execution tree with timings
- State transitions at each node
- RAG retrieval results and similarity scores (`doc_id`, citation spans)
- LLM prompt and completion for the recommendation step
- Interrupt and resume events

## Running Tests

```bash
python3.12 -m unittest discover -s graph/tests -p "test_*.py" -v
# or
python3.12 -m pytest graph/tests/ -v
```

## Project Structure

```
viridien-langGraph/
├── app/
│   ├── main.py              # FastAPI service — invoke, approve, sessions, status, UI
│   ├── TriageInput.py       # Pydantic input model
│   └── static/
│       └── index.html       # Two-tab UI (Customer + Admin)
├── graph/
│   ├── TriageState.py       # TypedDict state flowing through all nodes
│   ├── builder.py           # Graph + subgraph wiring; PostgresSaver setup
│   ├── rag_subgraph.py      # Agentic RAG subgraph (build_query/retrieve/grade)
│   └── nodes/
│       ├── ingest.py
│       ├── fetch_order.py
│       ├── search_orders.py
│       ├── classify.py
│       ├── kb_orchestrator.py   # Bridges main graph ↔ RAG subgraph
│       ├── propose_remedy.py    # Preview → LLM → interrupt → commit
│       ├── draft_reply.py
│       └── no_order_id.py
├── graph/tests/             # Unit tests for all nodes
├── requirements.txt
├── run.sh
└── run.py
```
