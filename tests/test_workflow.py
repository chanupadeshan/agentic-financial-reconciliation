import pandas as pd

from langgraph.types import Command

from src.agent.workflow import create_reconciliation_agent
from src.agent.prompts import InvestigationOutput

import src.agent.nodes as nodes


# ---------------------------------------------------------
# Sample data
# ---------------------------------------------------------

def sample_invoices():

    return pd.DataFrame([
        {
            "invoice_id": "INV-2026-000001",
            "vendor": "ABC Technologies Ltd",
            "amount": 1000.00,
            "currency": "USD",
            "date": "2026-01-10",
        },
        {
            "invoice_id": "INV-2026-000002",
            "vendor": "Nova Systems Ltd",
            "amount": 500.00,
            "currency": "USD",
            "date": "2026-01-12",
        },
        {
            "invoice_id": "INV-2026-000003",
            "vendor": "Global Finance Ltd",
            "amount": 800.00,
            "currency": "USD",
            "date": "2026-01-15",
        },
    ])


def sample_ledgers():

    return pd.DataFrame([
        {
            "ledger_entry_id": "LED-001",
            "invoice_id": "INV-2026-000001",
            "reference": "INV-2026-000001",
            "vendor": "ABC Technologies Ltd",
            "amount": 1000.00,
            "currency": "USD",
            "date": "2026-01-10",
        },
        {
            "ledger_entry_id": "LED-002",
            "invoice_id": "INV-2026-000002",
            "reference": "INV-2026-000002",
            "vendor": "Nova Systems Ltd",
            "amount": 500.00,
            "currency": "USD",
            "date": "2026-01-12",
        },
        {
            "ledger_entry_id": "LED-003",
            "invoice_id": "INV-2026-000003",
            "reference": "INV-2026-000003",
            "vendor": "Global Finance Ltd",
            "amount": 800.00,
            "currency": "USD",
            "date": "2026-01-15",
        },
    ])


def sample_banks():

    return pd.DataFrame([
        # Exact match
        {
            "transaction_id": "BANK-001",
            "reference": "INV-2026-000001",
            "vendor": "ABC Technologies Ltd",
            "amount": 1000.00,
            "currency": "USD",
            "date": "2026-01-10",
            "description": "Invoice payment",
        },

        # Vendor name variation
        {
            "transaction_id": "BANK-002",
            "reference": "INV-2026-000002",
            "vendor": "Nova Systems Limited",
            "amount": 500.00,
            "currency": "USD",
            "date": "2026-01-12",
            "description": "Invoice payment",
        },

        # Amount mismatch
        {
            "transaction_id": "BANK-003",
            "reference": "INV-2026-000003",
            "vendor": "Global Finance Ltd",
            "amount": 750.00,
            "currency": "USD",
            "date": "2026-01-15",
            "description": "Invoice payment",
        },

        # Bank-only transaction
        {
            "transaction_id": "BANK-999",
            "reference": "OTHER-TRANSACTION",
            "vendor": "Unknown Vendor",
            "amount": 300.00,
            "currency": "USD",
            "date": "2026-01-20",
            "description": "Unknown bank payment",
        },
    ])


# Exact match
def test_exact_match_auto_reconcile():

    graph = create_reconciliation_agent(
        sample_invoices(),
        sample_ledgers(),
        sample_banks(),
    )

    config = {
        "configurable": {"thread_id": "test-exact"}
    }

    result = graph.invoke(
        {"invoice_id": "INV-2026-000001"},
        config=config,
    )

    assert result["final_status"] == "AUTO_RECONCILED"

    assert (
        result["reconciliation_result"]["scenario"]
        == "exact"
    )

    assert result["evidence"] is not None


# ---------------------------------------------------------
# Invoice not found
# ---------------------------------------------------------

def test_invoice_not_found():

    graph = create_reconciliation_agent(
        sample_invoices(),
        sample_ledgers(),
        sample_banks(),
    )

    config = {
        "configurable": {
            "thread_id": "test-not-found"
        }
    }

    result = graph.invoke(
        {
            "invoice_id": "INV-9999"
        },
        config=config,
    )

    assert result["final_status"] == "INVOICE_NOT_FOUND"


# ---------------------------------------------------------
# Amount mismatch -> human review
# ---------------------------------------------------------

def test_amount_mismatch_human_review():

    graph = create_reconciliation_agent(
        sample_invoices(),
        sample_ledgers(),
        sample_banks(),
    )

    config = {
        "configurable": {
            "thread_id": "test-amount-mismatch"
        }
    }

    # First call reaches interrupt()
    graph.invoke(
        {
            "invoice_id": "INV-2026-000003"
        },
        config=config,
    )

    # Human rejects the case
    result = graph.invoke(
        Command(
            resume={
                "decision": "reject",
                "comment": "Amount does not match.",
            }
        ),
        config=config,
    )

    assert result["final_status"] == "HUMAN_REJECTED"

    assert (
        result["reconciliation_result"]["scenario"]
        == "amount_mismatch"
    )


# ---------------------------------------------------------
# Bank-only unmatched transaction
# ---------------------------------------------------------

def test_bank_only_transaction():

    graph = create_reconciliation_agent(
        sample_invoices(),
        sample_ledgers(),
        sample_banks(),
    )

    config = {
        "configurable": {
            "thread_id": "test-bank-only"
        }
    }

    graph.invoke(
        {
            "bank_transaction_id": "BANK-999"
        },
        config=config,
    )

    result = graph.invoke(
        Command(
            resume={
                "decision": "approve",
                "comment": "Reviewed manually.",
            }
        ),
        config=config,
    )

    assert (
        result["reconciliation_result"]["scenario"]
        == "bank_only_unmatched"
    )

    assert result["final_status"] == "HUMAN_APPROVED"


# ---------------------------------------------------------
# Fake structured LLM
# ---------------------------------------------------------

class FakeStructuredLLM:

    def invoke(self, messages):

        return InvestigationOutput(
            investigation_notes=(
                "Vendor names are slightly different "
                "but appear related."
            ),
            recommendation=(
                "Review the vendor identity before approval."
            ),
        )


# ---------------------------------------------------------
# Name variation -> LLM investigation -> human review
# ---------------------------------------------------------

def test_name_variation_investigation(monkeypatch):

    monkeypatch.setattr(
        nodes,
        "structured_llm",
        FakeStructuredLLM(),
    )

    graph = create_reconciliation_agent(
        sample_invoices(),
        sample_ledgers(),
        sample_banks(),
    )

    config = {
        "configurable": {
            "thread_id": "test-name-variation"
        }
    }

    graph.invoke(
        {
            "invoice_id": "INV-2026-000002"
        },
        config=config,
    )

    result = graph.invoke(
        Command(
            resume={
                "decision": "approve",
                "comment": "Vendor confirmed.",
            }
        ),
        config=config,
    )

    assert (
        result["reconciliation_result"]["scenario"]
        == "name_variation"
    )

    assert (
        result["investigation_notes"]
        == "Vendor names are slightly different but appear related."
    )

    assert (
        result["recommendation"]
        == "Review the vendor identity before approval."
    )

    assert result["final_status"] == "HUMAN_APPROVED"


# ---------------------------------------------------------
# Invalid input
# ---------------------------------------------------------

def test_invalid_input():

    graph = create_reconciliation_agent(
        sample_invoices(),
        sample_ledgers(),
        sample_banks(),
    )

    config = {
        "configurable": {
            "thread_id": "test-invalid-input"
        }
    }

    result = graph.invoke(
        {},
        config=config,
    )

    assert result["final_status"] == "ERROR"

    assert result["error_message"] is not None