# CSV Files Guide
## Agentic Financial Reconciliation and Audit Copilot

This document explains the four CSV files used in the project, what each file represents, the meaning of its columns, how the files are related, and how they are used during reconciliation.

---

# 1. Overview

The project uses four CSV files:

1. `invoices.csv`
2. `ledger_entries.csv`
3. `bank_transactions.csv`
4. `reconciliation_ground_truth.csv`

The first three files are the **real input data** used by the reconciliation system.

The fourth file, `reconciliation_ground_truth.csv`, is used only for **evaluation**.

The main idea is:

```text
Invoice
"What should be paid?"
        ↓
Ledger
"What did accounting record?"
        ↓
Bank
"What actually happened?"
        ↓
Reconciliation
"Do these records match?"
        ↓
Ground Truth
"Was the system's answer correct?"
```

---

# 2. `invoices.csv`

## Purpose

`invoices.csv` represents invoices received from suppliers.

An invoice tells the company:

- who should be paid,
- how much should be paid,
- when the invoice was issued,
- when payment is due,
- what was purchased,
- and the current invoice status.

The sample dataset contains about **2,000 invoice records**.

## Columns

| Column | Meaning |
|---|---|
| `invoice_id` | Unique ID of the invoice |
| `vendor_id` | Unique ID of the supplier |
| `vendor_name` | Supplier/company name |
| `invoice_date` | Date the invoice was issued |
| `due_date` | Date by which payment is expected |
| `currency` | Currency such as USD, GBP, EUR, or LKR |
| `subtotal` | Amount before tax |
| `tax_amount` | Tax amount |
| `total_amount` | Final invoice amount |
| `po_number` | Purchase order or purchasing reference |
| `cost_center` | Department or business cost area |
| `description` | Description of the goods or services |
| `invoice_status` | Status such as `PAID`, `OPEN`, or `REVIEW` |

## Example

```text
invoice_id:      INV-2026-000279
vendor_name:     Vertex Packaging Limited
invoice_date:    2026-01-01
currency:        GBP
total_amount:    22946.69
invoice_status:  PAID
```

This means:

> The company received an invoice from Vertex Packaging Limited for GBP 22,946.69.

## Important reconciliation fields

The most important fields are:

```text
invoice_id
vendor_name
invoice_date
currency
total_amount
```

During ingestion, these are standardized:

```text
vendor_name  → vendor
invoice_date → date
total_amount → amount
invoice_id   → reference
```

After cleaning, the reconciliation layer can use:

```text
invoice_id
vendor
date
amount
currency
reference
```

---

# 3. `ledger_entries.csv`

## Purpose

`ledger_entries.csv` represents the company's internal accounting records.

The invoice tells us what the supplier requested.

The ledger tells us what the accounting system recorded.

The sample dataset contains about **1,820 ledger entries**.

Not every ledger entry is necessarily a normal invoice payment. The dataset also contains transaction types such as:

```text
PAYMENT
ADJUSTMENT
REVERSAL
ACCRUAL
```

## Columns

| Column | Meaning |
|---|---|
| `ledger_entry_id` | Unique ID of the accounting entry |
| `invoice_id` | Invoice connected to the entry, when available |
| `vendor_id` | Supplier ID |
| `vendor_name` | Supplier name |
| `posting_date` | Date the entry was posted |
| `transaction_type` | Type such as PAYMENT, ACCRUAL, REVERSAL, or ADJUSTMENT |
| `amount` | Amount recorded in the ledger |
| `currency` | Currency of the ledger entry |
| `reference` | Reference used to identify or link the transaction |
| `gl_account` | General ledger account |
| `cost_center` | Department or cost center |
| `description` | Description of the accounting entry |
| `status` | Status of the ledger entry |

## Example

```text
ledger_entry_id: LED-0000235
invoice_id:      INV-2026-000279
vendor_name:     Vertex Packaging Limited
posting_date:    2026-01-19
transaction_type: PAYMENT
amount:          22946.69
currency:        GBP
reference:       INV-2026-000279
status:          POSTED
```

This means:

> The accounting system recorded a payment for invoice `INV-2026-000279`.

## Why both `invoice_id` and `reference` are useful

A ledger record can be connected to an invoice through:

```text
invoice_id
```

or:

```text
reference
```

Example:

```text
Target invoice:
INV-2026-000279

Possible ledger row:
invoice_id = INV-2026-000279

or

reference = INV-2026-000279
```

That is why the reconciliation code uses a function such as:

```python
get_related_ledgers()
```

Its job is to return the ledger entries related to one invoice.

## Important reconciliation fields

```text
ledger_entry_id
invoice_id
vendor_name
posting_date
amount
currency
reference
transaction_type
```

During ingestion:

```text
vendor_name  → vendor
posting_date → date
```

---

# 4. `bank_transactions.csv`

## Purpose

`bank_transactions.csv` represents the actual movement of money in the company's bank accounts.

The bank file answers:

> What money actually left or entered the bank account?

The sample dataset contains about **2,100 bank transactions**.

The file contains both invoice-related vendor payments and other financial transactions such as rent, tax, utilities, payroll-related items, and other expenses.

## Columns

| Column | Meaning |
|---|---|
| `transaction_id` | Unique bank transaction ID |
| `transaction_date` | Date the transaction occurred |
| `direction` | `DEBIT` or `CREDIT` |
| `amount` | Transaction amount |
| `currency` | Transaction currency |
| `counterparty_name` | Name of the other party |
| `counterparty_account` | Counterparty account number or identifier |
| `reference` | Payment reference, often containing an invoice ID |
| `payment_method` | WIRE, ACH, CHEQUE, BANK_TRANSFER, etc. |
| `bank_account` | Company's bank account involved |
| `description` | Description of the bank transaction |

## Example

```text
transaction_id:    BNK-00000260
transaction_date:  2026-01-19
direction:         DEBIT
amount:            22946.69
currency:          GBP
counterparty_name: Vertex Packaging Limited
reference:         INV-2026-000279
payment_method:    CHEQUE
```

This means:

> GBP 22,946.69 actually left the company's bank account for the invoice `INV-2026-000279`.

## Important reconciliation fields

```text
transaction_id
transaction_date
direction
amount
currency
counterparty_name
reference
description
```

During ingestion:

```text
counterparty_name → vendor
transaction_date  → date
```

---

# 5. `reconciliation_ground_truth.csv`

## Purpose

`reconciliation_ground_truth.csv` is used for **evaluation only**.

It contains the correct expected answer for each reconciliation case.

It is similar to an **answer sheet**.

The sample dataset contains about **2,180 ground-truth records**.

This file should **not** be used as input to the reconciliation logic or the agent.

## Columns

| Column | Meaning |
|---|---|
| `invoice_id` | Invoice related to the case, when applicable |
| `scenario` | Correct reconciliation scenario |
| `expected_action` | Correct action the system should take |
| `ledger_entry_ids` | Correct ledger record(s) connected to the case |
| `bank_transaction_ids` | Correct bank transaction(s) connected to the case |

## Example

```text
invoice_id:
INV-2026-000006

scenario:
duplicate_payment

expected_action:
FLAG_DUPLICATE_PAYMENT

ledger_entry_ids:
LED-0000005

bank_transaction_ids:
BNK-00000006|BNK-00000007
```

This means:

> The correct answer for invoice `INV-2026-000006` is that it has a duplicate payment and should be flagged.

## Why it is needed

Suppose the system predicts:

```text
Predicted scenario:
duplicate_payment

Predicted action:
FLAG_DUPLICATE_PAYMENT
```

And the ground truth says:

```text
Actual scenario:
duplicate_payment

Expected action:
FLAG_DUPLICATE_PAYMENT
```

Then:

```text
Prediction == Ground Truth
        ↓
      Correct
```

If they do not match:

```text
Prediction != Ground Truth
        ↓
      Incorrect
```

This allows us to calculate evaluation metrics such as:

```text
Accuracy
Precision
Recall
Exception recall
Auto-reconciliation precision
```

---

# 6. How the Files Work Together

The three operational CSV files represent three different views of the same financial process.

```text
Invoice
"What should be paid?"
        ↓
Ledger
"What did accounting record?"
        ↓
Bank
"What actually happened?"
```

The reconciliation system compares them.

Example:

```text
Invoice
INV-2026-000279
GBP 22946.69
        ↓
Ledger
INV-2026-000279
GBP 22946.69
        ↓
Bank
INV-2026-000279
GBP 22946.69
```

If the records agree, the result may be:

```text
scenario = exact
action = AUTO_RECONCILE
```

---

# 7. Main Relationships Between the Files

## Invoice → Ledger

The main relationship is:

```text
invoices.invoice_id
        ↕
ledger_entries.invoice_id
```

or:

```text
invoices.invoice_id
        ↕
ledger_entries.reference
```

This is why `get_related_ledgers()` searches both fields.

## Invoice → Bank

The main relationship is:

```text
invoices.invoice_id
        ↕
bank_transactions.reference
```

Example:

```text
Invoice ID:
INV-2026-000279

Bank Reference:
INV-2026-000279
```

Some split-payment cases may use references such as:

```text
INV-2026-000279-P1
INV-2026-000279-P2
```

These still belong to the same invoice.

---

# 8. What the Reconciliation System Compares

Once related records are found, the system compares important fields.

## Reference

Checks whether the records appear to belong to the same invoice.

## Amount

```text
Invoice amount
vs
Ledger amount
vs
Bank amount
```

## Currency

```text
Invoice: USD
Ledger:  USD
Bank:    USD
```

## Date

Dates may not always be exactly the same.

```text
Invoice date: 2026-01-01
Ledger date:  2026-01-19
Bank date:    2026-01-19
```

A larger or unexpected difference can become a `date_shift` case.

## Vendor

Example:

```text
Invoice vendor:
Seacrest Consulting Incorporated

Bank counterparty:
Seacrest Consulting Inc
```

These names may represent the same vendor even though the strings are different.

That is why the reconciliation layer uses:

```python
normalize_text()
vendor_similarity()
```

---

# 9. Main Reconciliation Scenarios

## Exact Match

```text
scenario = exact
action = AUTO_RECONCILE
```

## Name Variation

Example:

```text
Nova Systems Corporation
Nova Systems Corp
```

## Amount Mismatch

```text
Invoice: 1000
Ledger:  1000
Bank:     950
```

## Date Shift

```text
Ledger date: 2026-01-20
Bank date:   2026-01-25
```

## Duplicate Payment

```text
Invoice: 1000
Bank payment 1: 1000
Bank payment 2: 1000
```

Possible action:

```text
FLAG_DUPLICATE_PAYMENT
```

## Split Payment

```text
Invoice: 1000
Bank payment 1: 600
Bank payment 2: 400
```

## Missing Ledger Entry

```text
Invoice → exists
Ledger  → missing
Bank    → exists
```

## Missing Bank Payment

```text
Invoice → exists
Ledger  → exists
Bank    → missing
```

## Unpaid Invoice

No bank payment is found for the invoice.

## Bank Fee

The transaction amount may differ because of a bank fee.

## Bank-Only Transaction

A bank transaction exists but cannot be connected to an invoice.

---

# 10. Why the Ingestion Layer Renames Columns

The datasets use different names for similar concepts.

```text
Invoice: vendor_name
Ledger:  vendor_name
Bank:    counterparty_name
```

These become:

```text
vendor
```

Similarly:

```text
invoice_date
posting_date
transaction_date
```

become:

```text
date
```

And:

```text
total_amount
amount
amount
```

become:

```text
amount
```

This gives the reconciliation layer a simple common structure:

```text
vendor
date
amount
currency
reference
```

The original IDs are still kept:

```text
invoice_id
ledger_entry_id
transaction_id
```

---

# 11. Why Ground Truth Must Stay Separate

Correct flow:

```text
Invoices
Ledger
Bank
   ↓
Reconciliation System
   ↓
Predicted Result
   ↓
Compare With
Ground Truth
```

Incorrect flow:

```text
Ground Truth
   ↓
Reconciliation System
```

If the system sees the ground truth before making its prediction, the evaluation is invalid.

Remember:

> `reconciliation_ground_truth.csv` is the answer sheet used after reconciliation, not an input used during reconciliation.

---

# 12. Simple End-to-End Example

## Invoice

```text
invoice_id: INV-001
vendor: ABC Company
amount: 1000
currency: USD
```

## Ledger

```text
ledger_entry_id: LED-001
invoice_id: INV-001
vendor: ABC Company
amount: 1000
currency: USD
reference: INV-001
```

## Bank

```text
transaction_id: BNK-001
vendor: ABC Company
amount: 1000
currency: USD
reference: INV-001
```

The reconciliation system checks:

```text
Reference → Match
Vendor    → Match
Amount    → Match
Currency  → Match
```

Result:

```text
scenario = exact
action = AUTO_RECONCILE
```

Then the result is compared against the ground-truth file.

---

# 13. Quick Summary

| File | Main question |
|---|---|
| `invoices.csv` | What should the company pay? |
| `ledger_entries.csv` | What did the accounting system record? |
| `bank_transactions.csv` | What actually happened in the bank? |
| `reconciliation_ground_truth.csv` | What is the correct expected reconciliation result? |

The complete idea is:

```text
Expected Payment
      +
Accounting Record
      +
Actual Bank Movement
      ↓
Reconciliation
      ↓
Match / Anomaly
      ↓
Action
      ↓
Evaluation Using Ground Truth
```

This relationship is the foundation of the Agentic Financial Reconciliation and Audit Copilot.
