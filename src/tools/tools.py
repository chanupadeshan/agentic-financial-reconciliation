"""Tools exposed to the reconciliation agent."""

import pandas as pd 
from ..reconciliation.reconciliation import (
    get_related_ledgers,
    get_related_bank_transactions,
    reconcile_invoice,
    vendor_similarity
)

def get_invoice(invoice_id: str,invoice: pd.DataFrame) -> dict|None:
    """
        Find one invoice using its invoice ID.

        Example:
            invoice_id = "INV-2026-000279"

        Returns:
            dict:
                The invoice record if found.

            None:
                If the invoice does not exist.
    """

    match = invoice[invoice["invoice_id"].fillna("").astype(str).eq(str(invoice_id))]

    if match.empty:
        return None

    return match.iloc[0].to_dict()


def get_ledger_entries(invoice_id:str,ledger_entries:pd.DataFrame) -> list:
    """
        Find all ledger entries related to an invoice.

        The function uses the reconciliation layer's
        `get_related_ledgers()` function.

        Returns:
            list:
                Related ledger records as dictionaries.
    """

    related_ledgers = get_related_ledgers(invoice_id, ledger_entries)
    return related_ledgers.to_dict(orient="records")


def get_bank_transactions(invoice_id:str,bank_transactions:pd.DataFrame) -> list:
    """
        Find all bank transactions related to an invoice.

        This includes:
            - normal payments
            - split payments

        Returns:
            list:
                Related bank transactions as dictionaries.
    """

    related_transactions = get_related_bank_transactions(invoice_id, bank_transactions)
    return related_transactions.to_dict(orient="records")


def get_reconciliation_result(invoice_id:str,invoice:pd.DataFrame,ledger_entries:pd.DataFrame,bank_transactions:pd.DataFrame) -> dict|None:
    """
        Reconcile one invoice and return its reconciliation result.

        First, the function finds the invoice.

        Then it sends the invoice to `reconcile_invoice()` together
        with the ledger and bank transaction data.

        Returns:
            dict:
                Reconciliation result.

            None:
                If the invoice does not exist.
    """

    invoice_match = invoice[invoice["invoice_id"].fillna("").astype(str).eq(str(invoice_id))]

    if invoice_match.empty:
        return None

    invoice_record = invoice_match.iloc[0]

    return reconcile_invoice(invoice_record, ledger_entries, bank_transactions)

def search_vendor_transactions(vendor_name:str,invoices: pd.DataFrame,ledger_entries: pd.DataFrame,bank_transactions:pd.DataFrame,similarity_threshold:float=0.7) -> dict:

    """
        Search invoices, ledger entries, and bank transactions
        for records belonging to a vendor.

        Vendor names do not need to be exactly the same.

        Example:
            Search:
                "ABC Technologies Ltd"

            Possible record:
                "ABC Technologies Limited"

            If the vendor similarity is above the threshold,
            the record is included.

        Args:
            vendor_name (str):
                Vendor name to search for.

            invoices (pd.DataFrame):
                Invoice records.

            ledger_entries (pd.DataFrame):
                Ledger records.

            bank_transactions (pd.DataFrame):
                Bank transaction records.

            similarity_threshold (float):
                Minimum vendor similarity score.
                Default = 0.70

        Returns:
            dict:
                Matching invoice, ledger, and bank records.
    """

    invoice_matches = []
    ledger_matches = []
    bank_matches = []

    ## search invoices
    for _, invoice in invoices.iterrows():
        similarity = vendor_similarity(vendor_name,invoice["vendor"])

        if similarity is not None and similarity >= similarity_threshold:
            record = invoice.to_dict()
            record["vendor_similarity"] = similarity
            invoice_matches.append(record)

    for _,ledger in ledger_entries.iterrows():

        similarity = vendor_similarity(vendor_name,ledger["vendor"])

        if (similarity is not None and similarity >= similarity_threshold):
            record = ledger.to_dict()
            record["vendor_similarity"] = similarity
            ledger_matches.append(record)

    for _,bank in bank_transactions.iterrows():
        
        similarity = vendor_similarity(vendor_name,bank["vendor"])

        if (similarity is not None and similarity >= similarity_threshold):
            record = bank.to_dict()
            record["vendor_similarity"] = similarity
            bank_matches.append(record)

    return {
        "vendor": vendor_name,
        "invoices": invoice_matches,
        "ledger_entries": ledger_matches,
        "bank_transactions": bank_matches
    }