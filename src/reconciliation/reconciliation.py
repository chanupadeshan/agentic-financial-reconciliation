"""Core reconciliation logic."""
import re
from difflib import SequenceMatcher
import unicodedata
import pandas as pd

def normalize_text(value:str) -> str:
    """
    Normalize a text string by removing accents, converting to uppercase, and removing common company suffixes
    """

    ## handle missing values
    if pd.isna(value):
        return "" 
    
    ## convert to string
    text = str(value).strip()

    ## remove accents
    ## example : "Café" -> "Cafe"
    text = unicodedata.normalize("NFKD",text)
    text = "".join(char for char in text if not unicodedata.combining(char))

    ## convert to uppercase
    text = text.upper()

    ## normalize the common symbols
    text = text.replace("&"," AND ")
    text = text.replace("@"," AT ")
    text = text.replace("%"," PERCENT ")

    ## remove punctuations 
    text = re.sub(r"[^A-Z0-9\s]"," ",text)

    ## remove common comapany suffixes
    company_words = (
    r"\b(?:INC|INCORPORATED|LLC|LTD|LIMITED|CORP|CORPORATION|"
    r"CO|COMPANY|PVT|PRIVATE|PLC|LTDA|GMBH)\b"
    )   

    text = re.sub(company_words,"",text)

    ## remove extra spaces
    text = re.sub(r"\s+"," ",text).strip()

    return text 

def vendor_similarity(vendor1:str,vendor2:str) -> float | None:
    """
    compare two vendor names and return a similarity score between 0 and 1.
    return 1 if the names are identical, 0 if they are completely different 
    and None if either of the names is empty or missing.
    """

    normalized_vendor1 = normalize_text(vendor1)
    normalized_vendor2 = normalize_text(vendor2)

    if not normalized_vendor1 or not normalized_vendor2:
        return None

    ## use SequenceMatcher to calculate similarity
    similarity = SequenceMatcher(None,normalized_vendor1,normalized_vendor2).ratio()

    return round(similarity,2)


def get_related_ledgers(invoice_id:str,ledger_entries:pd.DataFrame) -> pd.DataFrame:
    """
        Find all ledger entries related to a specific invoice.

        The function checks both the `invoice_id` column and the `reference`
        column in the ledger DataFrame. A ledger entry is considered related
        if either field matches the given invoice ID.

        Missing values are replaced with empty strings before comparison to
        avoid errors.

        Example:
            invoice_id = "INV-2026-000279"

            Ledger data:

            ledger_entry_id   invoice_id          reference
            LED-001           INV-2026-000279     INV-2026-000279
            LED-002           INV-2026-000500     INV-2026-000500
            LED-003           NaN                 INV-2026-000279

            The function returns:
            LED-001 and LED-003

            because either `invoice_id` or `reference` matches
            "INV-2026-000279".

        Args:
            invoice_id (str):
                The invoice ID to search for.

            ledger_entries (pd.DataFrame):
                The DataFrame containing ledger records.

        Returns:
            pd.DataFrame:
                A DataFrame containing only the ledger entries related to
                the given invoice.
    """

    invoice_match = (
        ledger_entries["invoice_id"].fillna("").astype(str).eq(str(invoice_id))
    )

    reference_match = (
        ledger_entries["reference"].fillna("").astype(str).eq(str(invoice_id))
    )

    related_ledgers = ledger_entries[invoice_match | reference_match]

    return related_ledgers

def get_related_bank_transactions(invoice_id:str,bank_transactions:pd.DataFrame) -> pd.DataFrame:
    """
    Find all bank transactions related to a specific invoice.

    The function checks the bank transaction `reference` column.

    A transaction is considered related when:

    1. The reference exactly matches the invoice ID.

    Example:
        INV-2026-000279

    2. The reference starts with the invoice ID followed by "-".

    Example:
        INV-2026-000279-P1
        INV-2026-000279-P2

    This allows the function to find both normal payments and
    split payments related to the same invoice.
    """

    reference = (
        bank_transactions["reference"].fillna("").astype(str)
    )

    ## check bank transactions is exactly equal to the invoice_id
    exact_match = reference.eq(str(invoice_id))

    ## check bank transactions that start with the invoice_id followed by a -
    ## reason is sometimes the invoice is split into multiple payments, and the reference will be like INV-2026-000279-1, INV-2026-000279-2, etc.
    split_payments_match = reference.str.startswith(str(invoice_id) + "-")

    related_transactions = bank_transactions[exact_match | split_payments_match]

    return related_transactions


def reconcile_invoice(invoice: pd.Series,ledger_entries: pd.DataFrame,bank_transactions: pd.DataFrame) -> dict:
    """
    Reconcile one invoice with its related ledger entries and
    bank transactions.

    The function checks for:

        1. Unpaid invoice
        2. Missing ledger entry
        3. Missing bank payment
        4. Duplicate payment
        5. Split payment
        6. Bank fee
        7. Currency mismatch
        8. Amount mismatch
        9. Date shift
        10. Vendor name variation
        11. Exact match

    Args:
        invoice (pd.Series):
            One invoice record.

        ledger_entries (pd.DataFrame):
            All ledger records.

        bank_transactions (pd.DataFrame):
            All bank transaction records.

    Returns:
        dict:
            Reconciliation result containing the invoice ID,
            detected scenario, recommended action, and related
            ledger/bank IDs.
    """

    ## Get invoice information
    invoice_id = str(invoice["invoice_id"])
    invoice_amount = float(invoice["amount"])
    invoice_currency = str(invoice["currency"]).strip().upper()
    invoice_vendor = invoice["vendor"]

    ## find related ledger and bank records
    related_ledgers = get_related_ledgers(invoice_id,ledger_entries)

    related_bank_transactions = get_related_bank_transactions(invoice_id,bank_transactions)

    ## Save related IDs
    ledger_ids = related_ledgers["ledger_entry_id"].astype(str).tolist()
    bank_ids = (related_bank_transactions["transaction_id"].astype(str).tolist())

    ## No ledger + no bank transaction
    if related_ledgers.empty and related_bank_transactions.empty:
        return {
            "invoice_id": invoice_id,
            "scenario": "unpaid",
            "action": "NO_BANK_PAYMENT_EXPECTED",
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    ## Bank exists but ledger is missing
    if related_ledgers.empty and not related_bank_transactions.empty:
        return {
            "invoice_id": invoice_id,
            "scenario": "missing_ledger",
            "action": "FLAG_MISSING_LEDGER_ENTRY",
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    ## Ledger exists but bank payment is missing
    if not related_ledgers.empty and related_bank_transactions.empty:
        return {
            "invoice_id": invoice_id,
            "scenario": "missing_bank_payment",
            "action": "INVESTIGATE_MISSING_BANK_PAYMENT",
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    ## Check multiple bank transactions
    if len(related_bank_transactions) >= 2:

        bank_amounts = pd.to_numeric(related_bank_transactions["amount"],errors="coerce")

        ## Check for duplicate payment
        ## le: less than or equal to 
        exact_payment_count = ((bank_amounts - invoice_amount).abs().le(0.01).sum())

        if exact_payment_count >= 2:
            return {
                "invoice_id": invoice_id,
                "scenario": "duplicate_payment",
                "action": "FLAG_DUPLICATE_PAYMENT",
                "ledger_entry_ids": ledger_ids,
                "bank_transaction_ids": bank_ids
            }

        ## Split payment
        total_bank_amount = bank_amounts.sum()

        ## check if total_bank_amount is equal to invoice_amount (total_bank_amount - invoice_amount == 0)
        if abs(total_bank_amount - invoice_amount) <= 0.01:
            return {
                "invoice_id": invoice_id,
                "scenario": "split_payment",
                "action": "RECONCILE_SPLIT_PAYMENT",
                "ledger_entry_ids": ledger_ids,
                "bank_transaction_ids": bank_ids
            }

    ## Use first related ledger and bank record
    ledger = related_ledgers.iloc[0]
    bank = related_bank_transactions.iloc[0]

    ledger_amount = float(ledger["amount"])
    bank_amount = float(bank["amount"])

    ledger_currency = str(ledger["currency"]).strip().upper()
    bank_currency = str(bank["currency"]).strip().upper()

    ## Check for bank fee
    bank_description = str(bank.get("description", "")).lower()

    if "fee" in bank_description:
        return {
            "invoice_id": invoice_id,
            "scenario": "bank_fee",
            "action": "REVIEW_POSSIBLE_BANK_FEE",
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    ## Currency mismatch
    if (invoice_currency != ledger_currency or invoice_currency != bank_currency):
        return {
            "invoice_id": invoice_id,
            "scenario": "currency_mismatch",
            "action": "MANUAL_REVIEW_CURRENCY_MISMATCH",
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    ## Amount mismatch
    if (abs(invoice_amount - ledger_amount) > 0.01 or abs(invoice_amount - bank_amount) > 0.01):
        return {
            "invoice_id": invoice_id,
            "scenario": "amount_mismatch",
            "action": "MANUAL_REVIEW_AMOUNT_MISMATCH",
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    ## Date shift
    ledger_date = pd.to_datetime(ledger["date"])
    bank_date = pd.to_datetime(bank["date"])

    date_difference = abs((bank_date - ledger_date).days)

    if date_difference >= 3:
        return {
            "invoice_id": invoice_id,
            "scenario": "date_shift",
            "action": "INVESTIGATE_DATE_DIFFERENCE",
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    ## Vendor name variation
    bank_vendor = bank["vendor"]

    similarity = vendor_similarity(
        invoice_vendor,
        bank_vendor
    )

    invoice_vendor_basic = str(invoice_vendor).strip().upper()
    bank_vendor_basic = str(bank_vendor).strip().upper()

    if similarity is None:
        return {
            "invoice_id": invoice_id,
            "scenario": "vendor_name_missing",
            "action": "MANUAL_REVIEW_VENDOR_NAME_MISSING",
            "vendor_similarity": None,
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    if (invoice_vendor_basic != bank_vendor_basic and similarity >= 0.70):
        return {
            "invoice_id": invoice_id,
            "scenario": "name_variation",
            "action": "AUTO_RECONCILE_OR_LOW_RISK_REVIEW",
            "vendor_similarity": similarity,
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    ## Large vendor mismatch
    if similarity < 0.70:
        return {
            "invoice_id": invoice_id,
            "scenario": "vendor_mismatch",
            "action": "MANUAL_REVIEW_VENDOR_MISMATCH",
            "vendor_similarity": similarity,
            "ledger_entry_ids": ledger_ids,
            "bank_transaction_ids": bank_ids
        }

    ## Everything matches
    return {
        "invoice_id": invoice_id,
        "scenario": "exact",
        "action": "AUTO_RECONCILE",
        "vendor_similarity": similarity,
        "ledger_entry_ids": ledger_ids,
        "bank_transaction_ids": bank_ids
    }

def extract_invoice_id_from_reference(reference:str) -> str | None:
    """
        Find and return an invoice ID from a reference text.

        This function looks inside the given reference and searches for an
        invoice ID in this format:

            INV-YYYY-NNNNNN

        Example:
            reference = "Payment for INV-2026-000279"

            The function returns:
            "INV-2026-000279"

        Another example:
            reference = "INV-2026-000279-P1"

            The function still returns:
            "INV-2026-000279"

        This is useful for bank transactions because a bank reference may
        contain extra text together with the invoice ID.

        Args:
            reference (str):
                The reference text to search.

        Returns:
            str:
                The invoice ID if one is found.

            None:
                If the reference is empty or no invoice ID is found.
    """

    if pd.isna(reference):
        return None
    ## INV:exact text , \d{4}: 4 digits for year, \d{6}: 6 digits for invoice number
    match = re.search(r"INV-\d{4}-\d{6}", str(reference))

    if match:
        ## getting the invoice id from the reference(<re.Match object; span=(12, 27), match='INV-2026-000279'>)
        return match.group(0)
    
    return None

def find_bank_only_transactions(invoices:pd.DataFrame,bank_transactions:pd.DataFrame) -> list:
    """
        Find bank transactions that do not have a matching invoice.

        The function checks the `reference` column in the bank transactions
        DataFrame and compares it against the `invoice_id` column in the
        invoices DataFrame. A bank transaction is considered "bank-only" if
        its reference does not match any invoice ID.

        Missing values are replaced with empty strings before comparison to
        avoid errors.

        Example:
            Invoices:
                invoice_id
                INV-2026-000279
                INV-2026-000500

            Bank transactions:
                transaction_id   reference
                TXN-001          INV-2026-000279
                TXN-002          INV-2026-000500
                TXN-003          INV-2026-000999

            The function returns:
                TXN-003

            because its reference does not match any invoice ID.

        Args:
            invoices (pd.DataFrame):
                The DataFrame containing invoice records.

            bank_transactions (pd.DataFrame):
                The DataFrame containing bank transaction records.

        Returns:
            list:
                A list containing the unmatched bank transaction results.
    """

    invoice_ids = set(invoices["invoice_id"].fillna("").astype(str))

    unmatched_transactions = []
   ## iterrows() is a more efficient way to iterate over rows in a DataFrame
    for _, bank in bank_transactions.iterrows():
        extracted_invoice_id = extract_invoice_id_from_reference(
            bank["reference"]
        )

        if extracted_invoice_id not in invoice_ids:
            unmatched_transactions.append(
                {
                    "invoice_id": extracted_invoice_id,
                    "scenario": "bank_only_unmatched",
                    "action": "CLASSIFY_AS_NON_AP_OR_INVESTIGATE",
                    "ledger_entry_ids": [],
                    "bank_transaction_ids": [str(bank["transaction_id"])]
                }
            )
    
    return unmatched_transactions


def reconcile_all_invoices(invoices:pd.DataFrame,ledger_entries:pd.DataFrame,bank_transactions:pd.DataFrame) -> pd.DataFrame:
    """
        Reconcile all invoices against ledger entries and bank transactions.

        The function iterates over each invoice, reconciles it, and collects
        the results into a DataFrame.

        Args:
            invoices (pd.DataFrame):
                The DataFrame containing invoice records.

            ledger_entries (pd.DataFrame):
                The DataFrame containing ledger records.

            bank_transactions (pd.DataFrame):
                The DataFrame containing bank transaction records.

        Returns:
            pd.DataFrame:
                A DataFrame containing the reconciliation results for all
                invoices.
    """

    results = []
    
    ## Iterate over each invoice and reconcile it
    for _, invoice in invoices.iterrows():

        result = reconcile_invoice(
            invoice,
            ledger_entries,
            bank_transactions
        )

        results.append(result)

    ## find bank transactions that do not have a matching invoice
    bank_only_results = find_bank_only_transactions(invoices,bank_transactions)

    ## add them to the final results
    results.extend(bank_only_results)
    
    return pd.DataFrame(results)
