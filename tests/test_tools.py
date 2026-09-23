import pandas as pd

from src.tools.tools import (
    get_invoice,
    get_ledger_entries,
    get_bank_transactions,
    get_reconciliation_result,
    search_vendor_transactions,
)


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
            "vendor": "Nova Systems",
            "amount": 500.00,
            "currency": "USD",
            "date": "2026-01-12",
        },
    ])


def sample_ledgers():
    return pd.DataFrame([
        {
            "ledger_entry_id": "LED-001",
            "invoice_id": "INV-2026-000001",
            "reference": "INV-2026-000001",
            "vendor": "ABC Technologies Limited",
            "amount": 1000.00,
            "currency": "USD",
            "date": "2026-01-10",
        },
        {
            "ledger_entry_id": "LED-002",
            "invoice_id": "INV-2026-000002",
            "reference": "INV-2026-000002",
            "vendor": "Nova Systems",
            "amount": 500.00,
            "currency": "USD",
            "date": "2026-01-12",
        },
    ])


def sample_bank_transactions():
    return pd.DataFrame([
        {
            "transaction_id": "BANK-001",
            "reference": "INV-2026-000001",
            "vendor": "ABC Technologies Ltd",
            "amount": 1000.00,
            "currency": "USD",
            "date": "2026-01-10",
            "description": "Invoice payment",
        },
        {
            "transaction_id": "BANK-002",
            "reference": "INV-2026-000002",
            "vendor": "Nova Systems",
            "amount": 500.00,
            "currency": "USD",
            "date": "2026-01-12",
            "description": "Invoice payment",
        },
    ])



def test_get_invoice_found():

    invoices = sample_invoices()

    result = get_invoice("INV-2026-000001",invoices)

    assert result is not None
    assert result["invoice_id"] == "INV-2026-000001"
    assert result["vendor"] == "ABC Technologies Ltd"
    assert result["amount"] == 1000.00


def test_get_invoice_not_found():

    invoices = sample_invoices()

    result = get_invoice("INV-9999",invoices)

    assert result is None



def test_get_ledger_entries():

    ledgers = sample_ledgers()

    result = get_ledger_entries("INV-2026-000001",ledgers)

    assert len(result) == 1
    assert result[0]["ledger_entry_id"] == "LED-001"
    assert result[0]["invoice_id"] == "INV-2026-000001"



def test_get_bank_transactions():

    banks = sample_bank_transactions()

    result = get_bank_transactions("INV-2026-000001",banks)

    assert len(result) == 1
    assert result[0]["transaction_id"] == "BANK-001"
    assert result[0]["amount"] == 1000.00



def test_get_reconciliation_result():

    invoices = sample_invoices()
    ledgers = sample_ledgers()
    banks = sample_bank_transactions()

    result = get_reconciliation_result("INV-2026-000001",invoices,ledgers,banks)

    assert result is not None
    assert result["invoice_id"] == "INV-2026-000001"
    assert result["scenario"] == "exact"
    assert result["action"] == "AUTO_RECONCILE"


def test_get_reconciliation_result_invoice_not_found():

    invoices = sample_invoices()
    ledgers = sample_ledgers()
    banks = sample_bank_transactions()

    result = get_reconciliation_result("INV-9999",invoices,ledgers,banks)

    assert result is None


def test_search_vendor_transactions():

    invoices = sample_invoices()
    ledgers = sample_ledgers()
    banks = sample_bank_transactions()

    result = search_vendor_transactions("ABC Technologies Ltd",invoices,ledgers,banks)

    assert result["vendor"] == "ABC Technologies Ltd"

    assert len(result["invoices"]) == 1
    assert len(result["ledger_entries"]) == 1
    assert len(result["bank_transactions"]) == 1

    assert (result["invoices"][0]["invoice_id"] == "INV-2026-000001")