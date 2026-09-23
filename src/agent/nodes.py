import os

import pandas as pd
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.types import interrupt

from .prompts import (
    INVESTIGATION_SYSTEM_PROMPT,
    InvestigationOutput,
    build_investigation_prompt,
)
from .state import AgentState
from ..reconciliation.reconciliation import extract_invoice_id_from_reference
from ..tools.tools import (
    get_bank_transaction,
    get_bank_transactions,
    get_invoice,
    get_ledger_entries,
    get_reconciliation_result,
)

load_dotenv()


## LLM
llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), temperature=0)

structured_llm = llm.with_structured_output(InvestigationOutput)


def build_invoice_evidence(
    invoice: dict | None,
    ledger_entries: list,
    bank_transactions: list,
    reconciliation_result: dict | None,
) -> dict:
    """collect the important information about one reconciliation case into one dictionary.
       it stores the invoice, ledger entries ids, bank transactions ids and the reconciliation result."""

    return {
        "invoice": invoice,
        "ledger_entry_ids": [entry.get("ledger_entry_id") for entry in ledger_entries],
        "bank_transaction_ids": [entry.get("transaction_id") for entry in bank_transactions],
        "reconciliation_result": reconciliation_result,
    }


def create_load_case_node(
    invoices: pd.DataFrame,
    ledger_entries: pd.DataFrame,
    bank_transactions: pd.DataFrame,
):

    """
    create a node that loads a correct financial reconciliation case based on the invoice_id or bank_transaction_id in the state.
    It returns the invoice, ledger entries, bank transactions, reconciliation result and evidence in the state
    """
    
    def load_case(state: AgentState):
        try:
            invoice_id = state.get("invoice_id")
            bank_transaction_id = state.get("bank_transaction_id")

            ## invoice-based case
            if invoice_id:
                invoice_record = get_invoice(invoice_id, invoices)
                if invoice_record is None:
                    return {
                        "invoice": None,
                        "ledger_entries": [],
                        "bank_transactions": [],
                        "reconciliation_result": None,
                        "evidence": {"invoice_id": invoice_id},
                        "error_message": None,
                    }

                ledger = get_ledger_entries(invoice_id, ledger_entries)
                banks = get_bank_transactions(invoice_id, bank_transactions)
                result = get_reconciliation_result(
                    invoice_id, invoices, ledger_entries, bank_transactions
                )
                evidence = build_invoice_evidence(
                    invoice_record, ledger, banks, result
                )

                return {
                    "invoice": invoice_record,
                    "ledger_entries": ledger,
                    "bank_transactions": banks,
                    "reconciliation_result": result,
                    "evidence": evidence,
                    "error_message": None,
                }

            ## bank-transaction-based case
            if bank_transaction_id:
                bank = get_bank_transaction(bank_transaction_id, bank_transactions)
                if bank is None:
                    return {
                        "invoice": None,
                        "ledger_entries": [],
                        "bank_transactions": [],
                        "reconciliation_result": None,
                        "evidence": {"bank_transaction_id": bank_transaction_id},
                        "error_message": (f"Bank transaction {bank_transaction_id} not found."),
                    }

                reference = bank.get("reference")
                extracted_invoice_id = extract_invoice_id_from_reference(reference)
                known_invoice_ids = set(invoices["invoice_id"].fillna("").astype(str))

                ## bank transaction with known invoice
                if extracted_invoice_id in known_invoice_ids:
                    invoice_record = get_invoice(extracted_invoice_id, invoices)
                    ledger = get_ledger_entries(
                        extracted_invoice_id, ledger_entries
                    )
                    banks = get_bank_transactions(
                        extracted_invoice_id, bank_transactions
                    )
                    result = get_reconciliation_result(
                        extracted_invoice_id,
                        invoices,
                        ledger_entries,
                        bank_transactions,
                    )
                    evidence = build_invoice_evidence(
                        invoice_record, ledger, banks, result
                    )

                    return {
                        "invoice_id": extracted_invoice_id,
                        "invoice": invoice_record,
                        "ledger_entries": ledger,
                        "bank_transactions": banks,
                        "reconciliation_result": result,
                        "evidence": evidence,
                        "error_message": None,
                    }

                ## true bank-only unmatched transaction
                result = {
                    "invoice_id": extracted_invoice_id,
                    "scenario": "bank_only_unmatched",
                    "action": "CLASSIFY_AS_NON_AP_OR_INVESTIGATE",
                    "ledger_entry_ids": [],
                    "bank_transaction_ids": [str(bank["transaction_id"])],
                }

                evidence = {
                    "bank_transaction": bank,
                    "extracted_invoice_id": extracted_invoice_id,
                    "reconciliation_result": result,
                }

                return {
                    "invoice": None,
                    "ledger_entries": [],
                    "bank_transactions": [bank],
                    "reconciliation_result": result,
                    "evidence": evidence,
                    "error_message": None,
                }

            ## no valid input
            return {
                "error_message": (
                    "Provide either invoice_id or bank_transaction_id in the state."
                )
            }

        except Exception as e:
            return {"error_message": f"Error loading case: {str(e)}"}

    return load_case


## routing nodes
def route_case(state: AgentState):
    """
    route case node decides the next step in the workflow based on the reconciliation result and state.
    It returns the route to the next node in the workflow.
    """
    
    if state.get("error_message"):
        return "error"

    result = state.get("reconciliation_result")

    if result is None:
        return "not_found"

    scenario = result.get("scenario")

    if scenario in ["exact", "split_payment", "unpaid"]:
        return "auto"

    ## cases where LLM investigation is needed
    if scenario in ["name_variation", "date_shift", "bank_fee"]:
        return "investigate"

    ## higher-risk case
    return "human_review"


## auto finalize
def auto_finalize(state: AgentState):
    """
    auto finalize node determines the final status of the case based on the reconciliation result.
    It returns the final status and indicates that no human review is needed.
    """

    result = state["reconciliation_result"]
    scenario = result["scenario"]

    if scenario == "exact":
        final_status = "AUTO_RECONCILED"
    elif scenario == "split_payment":
        final_status = "RECONCILED_SPLIT_PAYMENT"
    elif scenario == "unpaid":
        final_status = "UNPAID"
    else:
        final_status = "COMPLETED"

    return {
        "route": "auto",
        "needs_human_review": False,
        "approved": True,
        "final_status": final_status,
    }


## LLM investigation node
def investigate_case(state: AgentState):
    """
    investigate_case node uses an LLM to analyze the reconciliation case and provide investigation notes and a recommendation.
    It returns the investigation notes, recommendation, and indicates that human review is needed.
    """
    
    try:
        prompt = build_investigation_prompt(state)
        result = structured_llm.invoke(
            [
                SystemMessage(content=INVESTIGATION_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )

        return {
            "route": "investigate",
            "investigation_notes": result.investigation_notes,
            "recommendation": result.recommendation,
            "needs_human_review": True,
            "error_message": None,
        }

    except Exception as e:
        return {
            "route": "investigate",
            "investigation_notes": "Automated investigation failed.",
            "recommendation": "Perform manual review.",
            "needs_human_review": True,
            "error_message": f"LLM investigation failed: {e}",
        }


## human review node
def human_review_case(state: AgentState):
    """
    human_review_case node allows a human to review the reconciliation case and make a decision.
    It returns the decision, comment, and indicates that no further human review is needed.
    """
    
    review = interrupt(
        {
            "invoice_id": state.get("invoice_id"),
            "bank_transaction_id": state.get("bank_transaction_id"),
            "reconciliation_result": state.get("reconciliation_result"),
            "evidence": state.get("evidence"),
            "investigation_notes": state.get("investigation_notes"),
            "recommendation": state.get("recommendation"),
            "error_message": state.get("error_message"),
            "options": ["approve", "reject"],
        }
    )

    decision = review.get("decision")
    comment = review.get("comment")
    approved = str(decision).lower() == "approve"

    return {
        "approved": approved,
        "human_comment": comment,
        "needs_human_review": False,
    }


## finalize human review
def finalize_review(state: AgentState):
    """
    finalize_review node determines the final status of the case based on the human review decision.
    It returns the final status and indicates that no further human review is needed.
    """
    
    if state.get("approved"):
        final_status = "HUMAN_APPROVED"
    else:
        final_status = "HUMAN_REJECTED"

    return {
        "route": "finalize",
        "final_status": final_status,
    }


## invoice not found
def invoice_not_found(state: AgentState):
    """
    invoice_not_found node handles cases where the invoice is not found in the system.
    It returns the final status and indicates that no human review is needed.
    """
    
    return {
        "route": "not_found",
        "needs_human_review": False,
        "approved": False,
        "final_status": "INVOICE_NOT_FOUND",
    }


## error
def handle_error(state: AgentState):
    """
    handle_error node handles cases where an error occurred during the workflow.
    It returns the final status and indicates that no human review is needed.
    """
    
    return {
        "route": "error",
        "needs_human_review": False,
        "approved": False,
        "final_status": "ERROR",
    }
