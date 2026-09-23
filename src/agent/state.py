from typing import TypedDict


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
    human_comment: str | None

    # Error handling
    error_message: str | None

    # Final result
    final_status: str