from pydantic import BaseModel

class TriageInput(BaseModel):
    ticket_text: str
    order_id: str | None = None