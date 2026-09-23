from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):

    # Input
    invoice_id: str | None
    bank_transaction_id: str | None

    # Financial records
    invoice: dict | None
    ledger_entries: list
    bank_transactions: list

    # Deterministic reconciliation result
    reconciliation_result: dict | None

    # Evidence used by the agent / reviewer
    evidence: dict

    # LLM investigation
    investigation_notes: str
    recommendation: str

    # Routing
    route: str
    needs_human_review: bool

    # Human review
    approved: bool | None
    reviewed_by: str | None
    reviewed_at: str | None
    human_comment: str | None

    # Error handling
    error_message: str | None

    # Final result
    final_status: str

    # Agent tool-calling conversation
    messages: Annotated[list[AnyMessage], add_messages]