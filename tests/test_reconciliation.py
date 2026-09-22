import pandas as pd
import pytest
from src.reconciliation.reconciliation import (
    normalize_text,
    vendor_similarity,
    get_related_ledgers,
    get_related_bank_transactions,
    reconcile_invoice,
    extract_invoice_id_from_reference,
    find_bank_only_transactions,
    reconcile_all_invoices,
)

def make_invoice(invoice_id="INV-2026-000001",amount=1000.0,currency="USD",vendor="ABC Technologies Ltd"):
    return pd.Series(
        {
            "invoice_id": invoice_id,
            "amount": amount,
            "currency": currency,
            "vendor": vendor,
        }
    )

def make_ledger_df(rows=None):
    if rows is None:
        rows = []
    columns = [
            "ledger_entry_id",
            "invoice_id",
            "reference",
            "amount",
            "currency",
            "date"
        ]
    return pd.DataFrame(rows, columns=columns)

def make_bank_df(rows=None):
    if rows is None:
        rows = []
    columns = [
            "transaction_id",
            "reference",
            "amount",
            "currency",
            "date",
            "vendor",
            "description",
        ]
    return pd.DataFrame(rows, columns=columns)

def test_normalize_text_removes_suffixes_and_normalizes_case():
    assert normalize_text("ABC Technologies Ltd") == "ABC TECHNOLOGIES"
    assert normalize_text("XYZ Company Inc.") == "XYZ"
    assert normalize_text("LMN Corporation LLC") == "LMN"
    assert normalize_text("PQR Enterprises Co.") == "PQR ENTERPRISES"

def test_normalize_text_handles_symbols_and_accents():
    assert normalize_text("Café & Restaurant") == "CAFE AND RESTAURANT"
    assert normalize_text("München GmbH") == "MUNCHEN"
    assert normalize_text("São Paulo Ltda.") == "SAO PAULO"

def test_normalize_text_returns_empty_string_for_missing_values():
    assert normalize_text(None) == ""
    assert normalize_text("") == ""
    assert normalize_text(float("nan")) == ""

def test_vendor_similarity_for_equaivalent_company_names():
    assert vendor_similarity("ABC Technologies Ltd", "ABC Technologies") == 1.0
    assert vendor_similarity("XYZ Company Inc.", "XYZ Company") == 1.0
    assert vendor_similarity("LMN Corporation LLC", "LMN Corporation") == 1.0
    assert vendor_similarity("PQR Enterprises Co.", "PQR Enterprises") == 1.0

def test_vendor_similarity_for_different_company_names():
    assert vendor_similarity("ABC Technologies Ltd", "XYZ Company") < 0.5
    assert vendor_similarity("LMN Corporation LLC", "PQR Enterprises") < 0.5
    assert vendor_similarity("Café & Restaurant", "München GmbH") < 0.5
    assert vendor_similarity("São Paulo Ltda.", "Berlin GmbH") < 0.5

def test_vendor_similarity_for_partial_matches():
    assert vendor_similarity("ABC Technologies Ltd", "ABC Tech") > 0.5
    assert vendor_similarity("XYZ Company Inc.", "XYZ Co.") > 0.5
    assert vendor_similarity("LMN Corporation LLC", "LMN Corp") > 0.5
    assert vendor_similarity("PQR Enterprises Co.", "PQR Ent.") > 0.5

def test_vendor_similarity_for_empty_or_missing_values():
    assert vendor_similarity("", "XYZ Company") is None
    assert vendor_similarity("LMN Corporation LLC", None) is None
    assert vendor_similarity(float("nan"), "PQR Enterprises") is None
    assert vendor_similarity("Café & Restaurant", "") is None

def test_get_related_ledgers_matches_invoice_id_or_reference():
    ledger = make_ledger_df(
        [
                {
                    "ledger_entry_id": "LED-001",
                    "invoice_id": "INV-2026-000279",
                    "reference": "INV-2026-000279",
                    "amount": 1000.00,
                    "currency": "USD",
                    "date": "2026-09-01",
                },

                {
                    "ledger_entry_id": "LED-002",
                    "invoice_id": "INV-2026-000500",
                    "reference": "INV-2026-000500",
                    "amount": 500.00,
                    "currency": "USD",
                    "date": "2026-09-01",
                },

                {
                    "ledger_entry_id": "LED-003",
                    "invoice_id": pd.NA,
                    "reference": "INV-2026-000279",
                    "amount": 1000.00,
                    "currency": "USD",
                    "date": "2026-09-01",
                },

        ]
    )

    result = get_related_ledgers("INV-2026-000279", ledger)

    assert len(result) == 2
    assert set(result["ledger_entry_id"]) == {"LED-001", "LED-003"}


def test_get_related_bank_transactions_finds_exact_and_split_reference():
    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000279",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment",
            },

            {
                "transaction_id": "BNK-002",
                "reference": "INV-2026-000279-P1",
                "amount": 600.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Part payment 1",
            },

            {
                "transaction_id": "BNK-003",
                "reference": "INV-2026-000279-P2",
                "amount": 400.00,
                "currency": "USD",
                "date": "2026-09-02",
                "vendor": "ABC Technologies Ltd",
                "description": "Part payment 2",
            },

            {
                "transaction_id": "BNK-004",
                "reference": "INV-2026-999999",
                "amount": 900.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "Other Vendor",
                "description": "Other payment",
            },
        ]
    )

    result = get_related_bank_transactions("INV-2026-000279", banks)

    assert len(result) == 3
    assert set(result["transaction_id"]) == {"BNK-001", "BNK-002", "BNK-003"}


def test_reconcile_invoice_unpaid():
    invoice = make_invoice()
    result = reconcile_invoice(
        invoice,
        make_ledger_df(),
        make_bank_df()
    )

    assert result["scenario"] == "unpaid"
    assert result["action"] == "NO_BANK_PAYMENT_EXPECTED"


def test_reconcile_invoice_missing_ledger():
    invoice = make_invoice()

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment",
            }
        ]
    )

    result = reconcile_invoice(invoice, make_ledger_df(), banks)

    assert result["scenario"] == "missing_ledger"
    assert result["action"] == "FLAG_MISSING_LEDGER_ENTRY"

def test_reconcile_invoice_duplicate_payment():
    invoice = make_invoice()

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001-P1",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment",
            },
            {
                "transaction_id": "BNK-002",
                "reference": "INV-2026-000001-P2",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment",
            },
        ]
    )

    result = reconcile_invoice(invoice,ledgers,banks)

    assert result["scenario"] == "duplicate_payment"
    assert result["action"] == "FLAG_DUPLICATE_PAYMENT"
    assert len(result["bank_transaction_ids"]) == 2

def test_reconcile_invoice_missing_bank_payment():
    invoice = make_invoice()

    ledgers = make_ledger_df(
        [
                        {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    result = reconcile_invoice(invoice, ledgers, make_bank_df())

    assert result["scenario"] == "missing_bank_payment"
    assert result["action"] == "INVESTIGATE_MISSING_BANK_PAYMENT"


def test_reconcile_invoice_split_payment():
    invoice = make_invoice(amount=1000.00)

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001-P1",
                "amount": 600.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Part payment 1",
            },

            {
                "transaction_id": "BNK-002",
                "reference": "INV-2026-000001-P2",
                "amount": 400.00,
                "currency": "USD",
                "date": "2026-09-02",
                "vendor": "ABC Technologies Ltd",
                "description": "Part payment 2",
            },
        ]
    )

    result = reconcile_invoice(invoice, ledgers, banks)

    assert result["scenario"] == "split_payment"
    assert result["action"] == "RECONCILE_SPLIT_PAYMENT"

def test_reconcile_invoice_bank_fee():
    invoice = make_invoice(amount=1000.00)

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1005.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment including bank fee",
            }
        ]
    )

    result = reconcile_invoice(invoice, ledgers, banks)

    assert result["scenario"] == "bank_fee"
    assert result["action"] == "REVIEW_POSSIBLE_BANK_FEE"

def test_reconcile_invoice_currency_mismatch():
    invoice = make_invoice(currency="USD")

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "GBP",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment",
            }
        ]
    )

    result = reconcile_invoice(invoice, ledgers, banks)

    assert result["scenario"] == "currency_mismatch"
    assert result["action"] == "MANUAL_REVIEW_CURRENCY_MISMATCH"


def test_reconcile_invoice_amount_mismatch():
    invoice = make_invoice(amount=1000.00)

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1100.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment",
            }
        ]
    )

    result = reconcile_invoice(invoice, ledgers, banks)

    assert result["scenario"] == "amount_mismatch"
    assert result["action"] == "MANUAL_REVIEW_AMOUNT_MISMATCH"


def test_reconcile_invoice_date_shift():
    invoice = make_invoice()

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-05",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment",
            }
        ]
    )

    result = reconcile_invoice(invoice, ledgers, banks)

    assert result["scenario"] == "date_shift"
    assert result["action"] == "INVESTIGATE_DATE_DIFFERENCE"


def test_reconcile_invoice_vendor_name_missing():
    invoice = make_invoice(vendor="ABC Technologies Ltd")

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": pd.NA,
                "description": "Vendor payment",
            }
        ]
    )

    result = reconcile_invoice(invoice, ledgers, banks)

    assert result["scenario"] == "vendor_name_missing"
    assert result["action"] == "MANUAL_REVIEW_VENDOR_NAME_MISSING"
    assert result["vendor_similarity"] is None


def test_reconcile_invoice_name_variation():
    invoice = make_invoice(vendor="Nova Systems Corporation")

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "Nova Systems Corp",
                "description": "Vendor payment",
            }
        ]
    )

    result = reconcile_invoice(invoice, ledgers, banks)

    assert result["scenario"] == "name_variation"
    assert result["action"] == "AUTO_RECONCILE_OR_LOW_RISK_REVIEW"
    assert result["vendor_similarity"] == 1.0


def test_reconcile_invoice_vendor_mismatch():
    invoice = make_invoice(vendor="ABC Technologies Ltd")

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "Green Foods International",
                "description": "Vendor payment",
            }
        ]
    )

    result = reconcile_invoice(invoice, ledgers, banks)

    assert result["scenario"] == "vendor_mismatch"
    assert result["action"] == "MANUAL_REVIEW_VENDOR_MISMATCH"


def test_reconcile_invoice_exact_match():
    invoice = make_invoice(vendor="ABC Technologies Ltd")

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment",
            }
        ]
    )

    result = reconcile_invoice(invoice, ledgers, banks)

    assert result["scenario"] == "exact"
    assert result["action"] == "AUTO_RECONCILE"
    assert result["vendor_similarity"] == 1.0


@pytest.mark.parametrize(
    "reference, expected",
    [
        ("INV-2026-000279", "INV-2026-000279"),
        ("Payment for INV-2026-000279", "INV-2026-000279"),
        ("INV-2026-000279-P1", "INV-2026-000279"),
        ("MISC-002045", None),
        (pd.NA, None),
    ],
)
def test_extract_invoice_id_from_reference(reference, expected):
    assert extract_invoice_id_from_reference(reference) == expected


def test_find_bank_only_transactions_returns_only_unmatched_banks():
    invoices = pd.DataFrame(
        [
            {"invoice_id": "INV-2026-000001"},
            {"invoice_id": "INV-2026-000002"},
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 100.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Ltd",
                "description": "Payment",
            },

            {
                "transaction_id": "BNK-002",
                "reference": "INV-2026-999999",
                "amount": 200.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "Other Ltd",
                "description": "Payment",
            },

            {
                "transaction_id": "BNK-003",
                "reference": "MISC-12345",
                "amount": 300.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "Unknown",
                "description": "Misc payment",
            },
        ]
    )

    result = find_bank_only_transactions(invoices, banks)

    assert len(result) == 2

    unmatched_ids = {
        item["bank_transaction_ids"][0]
        for item in result
    }

    assert unmatched_ids == {"BNK-002", "BNK-003"}
    assert all(item["scenario"] == "bank_only_unmatched" for item in result)


def test_reconcile_all_invoices_combines_invoice_results_and_bank_only_results():
    invoices = pd.DataFrame(
        [
            {
                "invoice_id": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "vendor": "ABC Technologies Ltd",
            }
        ]
    )

    ledgers = make_ledger_df(
        [
            {
                "ledger_entry_id": "LED-001",
                "invoice_id": "INV-2026-000001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
            }
        ]
    )

    banks = make_bank_df(
        [
            {
                "transaction_id": "BNK-001",
                "reference": "INV-2026-000001",
                "amount": 1000.00,
                "currency": "USD",
                "date": "2026-09-01",
                "vendor": "ABC Technologies Ltd",
                "description": "Vendor payment",
            },

            {
                "transaction_id": "BNK-999",
                "reference": "MISC-00999",
                "amount": 250.00,
                "currency": "USD",
                "date": "2026-09-02",
                "vendor": "Unknown Vendor",
                "description": "Miscellaneous payment",
            },
        ]
    )

    result = reconcile_all_invoices(invoices, ledgers, banks)

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2
    assert set(result["scenario"]) == {
        "exact",
        "bank_only_unmatched",
    }
