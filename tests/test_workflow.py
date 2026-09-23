import pandas as pd

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from src.agent.agent_tools import create_investigation_tools
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

def test_amount_mismatch_human_review(monkeypatch):

    monkeypatch.setattr(nodes, "llm", FakeNoToolLLM())

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
                "reviewed_by": "Asha Perera",
                "comment": "Amount does not match.",
            }
        ),
        config=config,
    )

    assert result["final_status"] == "HUMAN_REJECTED"
    assert result["reviewed_by"] == "Asha Perera"
    assert result["reviewed_at"].endswith("+00:00")
    assert result["human_comment"] == "Amount does not match."

    assert (
        result["reconciliation_result"]["scenario"]
        == "amount_mismatch"
    )


# ---------------------------------------------------------
# Bank-only unmatched transaction
# ---------------------------------------------------------

def test_bank_only_transaction(monkeypatch):

    monkeypatch.setattr(nodes, "llm", FakeNoToolLLM())

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


class FakeNoToolLLM:

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return AIMessage(content="The supplied evidence is sufficient.")


class FakeToolCallingLLM:

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        if any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(content="Invoice evidence gathered.")

        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "lookup_invoice",
                    "args": {"invoice_id": "INV-2026-000003"},
                    "id": "lookup-invoice-1",
                    "type": "tool_call",
                }
            ],
        )


def test_investigation_tool_schemas_hide_dataframes():
    tools = create_investigation_tools(
        sample_invoices(),
        sample_ledgers(),
        sample_banks(),
    )

    tool_fields = {
        investigation_tool.name: set(
            investigation_tool.args_schema.model_fields
        )
        for investigation_tool in tools
    }

    assert tool_fields == {
        "lookup_invoice": {"invoice_id"},
        "lookup_ledger_entries": {"invoice_id"},
        "lookup_bank_transactions": {"invoice_id"},
        "search_vendor": {"vendor_name"},
    }



def test_investigation_agent_executes_requested_tool(monkeypatch):
    monkeypatch.setattr(nodes, "llm", FakeToolCallingLLM())
    monkeypatch.setattr(nodes, "structured_llm", FakeStructuredLLM())

    graph = create_reconciliation_agent(
        sample_invoices(),
        sample_ledgers(),
        sample_banks(),
    )
    config = {
        "configurable": {"thread_id": "test-tool-investigation"}
    }

    result = graph.invoke(
        {"invoice_id": "INV-2026-000003"},
        config=config,
    )

    tool_messages = [
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage)
    ]

    assert len(tool_messages) == 1
    assert tool_messages[0].name == "lookup_invoice"
    assert "INV-2026-000003" in str(tool_messages[0].content)
    assert "__interrupt__" in result



# ---------------------------------------------------------
# Name variation -> LLM investigation -> human review
# ---------------------------------------------------------

def test_name_variation_investigation(monkeypatch):

    monkeypatch.setattr(nodes, "llm", FakeNoToolLLM())
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
# Routing and evidence regressions
# ---------------------------------------------------------

def test_every_anomaly_routes_to_investigation():
    anomaly_scenarios = [
        "amount_mismatch",
        "duplicate_payment",
        "missing_ledger",
        "missing_bank_payment",
        "bank_only_unmatched",
        "date_shift",
        "bank_fee",
        "name_variation",
        "vendor_mismatch",
        "currency_mismatch",
    ]

    for scenario in anomaly_scenarios:
        assert nodes.route_case(
            {"reconciliation_result": {"scenario": scenario}}
        ) == "investigate"


def test_invoice_evidence_is_compact():
    invoice = {
        "invoice_id": "INV-1",
        "vendor": "Example Vendor",
        "amount": 1000.0,
        "currency": "USD",
        "date": "2026-01-01",
        "unused_column": "must not reach the LLM",
    }
    ledgers = [
        {
            "ledger_entry_id": "LED-1",
            "amount": 1000.0,
            "unused_column": "hidden",
        }
    ]
    banks = [
        {
            "transaction_id": "BANK-1",
            "amount": 950.0,
            "unused_column": "hidden",
        }
    ]
    result = {
        "scenario": "amount_mismatch",
        "action": "MANUAL_REVIEW_AMOUNT_MISMATCH",
    }

    evidence = nodes.build_invoice_evidence(
        invoice,
        ledgers,
        banks,
        result,
    )

    assert evidence == {
        "invoice_id": "INV-1",
        "vendor": "Example Vendor",
        "invoice_amount": 1000.0,
        "invoice_currency": "USD",
        "invoice_date": "2026-01-01",
        "ledger_entry_ids": ["LED-1"],
        "bank_transaction_ids": ["BANK-1"],
        "ledger_entry_count": 1,
        "bank_transaction_count": 1,
        "scenario": "amount_mismatch",
        "action": "MANUAL_REVIEW_AMOUNT_MISMATCH",
        "vendor_similarity": None,
    }


def test_investigation_tools_limit_and_compact_records():
    invoice_id = "INV-2026-000001"
    ledgers = pd.DataFrame(
        [
            {
                "ledger_entry_id": f"LED-{index}",
                "invoice_id": invoice_id,
                "reference": invoice_id,
                "vendor": "ABC Technologies Ltd",
                "amount": 1000.0,
                "currency": "USD",
                "date": "2026-01-10",
                "unused_column": "hidden",
            }
            for index in range(7)
        ]
    )
    banks = pd.DataFrame(
        [
            {
                "transaction_id": f"BANK-{index}",
                "reference": f"{invoice_id}-P{index}",
                "vendor": "ABC Technologies Ltd",
                "amount": 100.0,
                "currency": "USD",
                "date": "2026-01-10",
                "description": "Part payment",
                "unused_column": "hidden",
            }
            for index in range(7)
        ]
    )
    tools = {
        investigation_tool.name: investigation_tool
        for investigation_tool in create_investigation_tools(
            sample_invoices(),
            ledgers,
            banks,
        )
    }

    ledger_result = tools["lookup_ledger_entries"].invoke(
        {"invoice_id": invoice_id}
    )
    bank_result = tools["lookup_bank_transactions"].invoke(
        {"invoice_id": invoice_id}
    )
    vendor_result = tools["search_vendor"].invoke(
        {"vendor_name": "ABC Technologies Ltd"}
    )

    assert len(ledger_result) == 5
    assert len(bank_result) == 5
    assert len(vendor_result["ledger_entries"]) == 5
    assert len(vendor_result["bank_transactions"]) == 5
    assert "unused_column" not in ledger_result[0]
    assert "unused_column" not in bank_result[0]


def test_finalize_investigation_limits_message_history(monkeypatch):
    captured_prompts = []

    class CapturingStructuredLLM:
        def invoke(self, messages):
            captured_prompts.append(messages[-1].content)
            return InvestigationOutput(
                investigation_notes="Bounded investigation.",
                recommendation="Review the compact evidence.",
            )

    monkeypatch.setattr(
        nodes,
        "structured_llm",
        CapturingStructuredLLM(),
    )
    messages = [
        AIMessage(content=f"message-{index}:" + ("x" * 4000))
        for index in range(8)
    ]

    result = nodes.finalize_investigation(
        {
            "reconciliation_result": {"scenario": "date_shift"},
            "evidence": {"invoice_id": "INV-1"},
            "messages": messages,
        }
    )

    prompt = captured_prompts[0]
    assert "message-0:" not in prompt
    assert "message-1:" not in prompt
    for index in range(2, 8):
        assert f"message-{index}:" in prompt
    assert "x" * 3001 not in prompt
    assert "Exact Deterministic Rule:" in prompt
    assert "ledger posting date and the bank transaction date" in prompt
    assert "The invoice date is NOT used to trigger this rule." in prompt
    assert result["error_message"] is None



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