"""Controlled, size-limited tools for the investigation agent."""

import pandas as pd
from langchain_core.tools import tool

from ..tools.tools import (
    get_bank_transactions,
    get_invoice,
    get_ledger_entries,
    search_vendor_transactions,
)

MAX_TOOL_RECORDS = 5


def _compact_record(record: dict, fields: tuple[str, ...]) -> dict:
    """Keep only fields that are useful to a financial investigation."""

    return {field: record.get(field) for field in fields}


def _compact_invoice(record: dict) -> dict:
    return _compact_record(
        record,
        ("invoice_id", "vendor", "amount", "currency", "date", "reference"),
    )


def _compact_ledger(record: dict) -> dict:
    return _compact_record(
        record,
        (
            "ledger_entry_id",
            "invoice_id",
            "vendor",
            "amount",
            "currency",
            "date",
            "reference",
        ),
    )


def _compact_bank(record: dict) -> dict:
    return _compact_record(
        record,
        (
            "transaction_id",
            "vendor",
            "amount",
            "currency",
            "date",
            "reference",
            "description",
        ),
    )


def create_investigation_tools(
    invoices: pd.DataFrame,
    ledger_entries: pd.DataFrame,
    bank_transactions: pd.DataFrame,
):
    """Create bounded tools with financial DataFrames hidden in closures."""

    @tool
    def lookup_invoice(invoice_id: str) -> dict:
        """Get compact invoice information for a specific invoice ID."""
        result = get_invoice(invoice_id, invoices)
        if result is None:
            return {"found": False, "invoice_id": invoice_id}
        return {"found": True, "invoice": _compact_invoice(result)}

    @tool
    def lookup_ledger_entries(invoice_id: str) -> list:
        """Get up to five compact ledger entries associated with an invoice."""
        records = get_ledger_entries(invoice_id, ledger_entries)
        return [
            _compact_ledger(record)
            for record in records[:MAX_TOOL_RECORDS]
        ]

    @tool
    def lookup_bank_transactions(invoice_id: str) -> list:
        """Get up to five compact bank transactions for an invoice."""
        records = get_bank_transactions(invoice_id, bank_transactions)
        return [
            _compact_bank(record)
            for record in records[:MAX_TOOL_RECORDS]
        ]

    @tool
    def search_vendor(vendor_name: str) -> dict:
        """Search up to five compact records per source for a vendor."""
        result = search_vendor_transactions(
            vendor_name,
            invoices,
            ledger_entries,
            bank_transactions,
        )

        return {
            "invoices": [
                _compact_invoice(record)
                for record in result.get("invoices", [])[:MAX_TOOL_RECORDS]
            ],
            "ledger_entries": [
                _compact_ledger(record)
                for record in result.get("ledger_entries", [])[:MAX_TOOL_RECORDS]
            ],
            "bank_transactions": [
                _compact_bank(record)
                for record in result.get("bank_transactions", [])[:MAX_TOOL_RECORDS]
            ],
        }

    return [
        lookup_invoice,
        lookup_ledger_entries,
        lookup_bank_transactions,
        search_vendor,
    ]
