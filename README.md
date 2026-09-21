# Agentic Financial Reconciliation and Audit Copilot

## Overview

The **Agentic Financial Reconciliation and Audit Copilot** is an AI-assisted financial reconciliation system that compares supplier invoices, ledger entries, and bank transactions.

The system uses deterministic rules for straightforward reconciliation cases and uses an LLM only when a case is ambiguous and requires investigation, explanation, or human review.

The project focuses on building a reliable and understandable financial reconciliation workflow using Python, LangGraph, PostgreSQL, FastAPI, Streamlit, and Docker.

---

## Business Problem

Financial teams often need to compare:

- Supplier invoices
- Internal ledger entries
- Bank transactions

These records may not always match perfectly.

Common issues include:

- Vendor name variations
- Amount mismatches
- Date differences
- Duplicate payments
- Split payments
- Missing ledger entries
- Missing bank payments
- Unpaid invoices
- Bank fees
- Unmatched bank transactions

Manually checking these cases can take a lot of time.

This project helps automate normal reconciliation cases and sends uncertain cases for further investigation or human review.

---

## Main Objectives

The main objectives of this project are:

- Load and validate financial CSV files.
- Clean and standardize financial data.
- Match invoices, ledger entries, and bank transactions.
- Detect reconciliation anomalies.
- Use deterministic logic before using an LLM.
- Use LangGraph to control the reconciliation workflow.
- Send uncertain cases to human review.
- Store reconciliation results in a database.
- Provide an API and dashboard.
- Evaluate the system using a separate ground-truth dataset.

---

## System Architecture

```text
CSV Files
   |
   v
Ingestion
   |
   v
Validation and Cleaning
   |
   v
Reconciliation Logic
   |
   v
Tools
   |
   v
LangGraph Agent
   |
   +----------------------+
   |                      |
   v                      v
Auto Reconcile        Investigation
                          |
                          v
                     Human Review
                          |
                          v
                      Final Result
                          |
                          v
                       Database
                          |
                   +------+------+
                   |             |
                   v             v
                FastAPI      Streamlit
```

---

## Project Structure

```text
agentic-financial-reconciliation/
│
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
│
├── data/
│   ├── raw/
│   │   ├── bank_transactions.csv
│   │   ├── ledger_entries.csv
│   │   └── invoices.csv
│   │
│   └── evaluation/
│       └── reconciliation_ground_truth.csv
│
├── src/
│   ├── ingestion/
│   │   ├── loader.py
│   │   └── validators.py
│   │
│   ├── reconciliation/
│   │   └── reconciliation.py
│   │
│   ├── tools/
│   │   └── tools.py
│   │
│   ├── agent/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── prompts.py
│   │   └── workflow.py
│   │
│   ├── database/
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── repository.py
│   │
│   ├── services/
│   │   └── reconciliation_service.py
│   │
│   └── main.py
│
├── api/
│   └── main.py
│
├── dashboard/
│   └── app.py
│
├── evaluation/
│   ├── metrics.py
│   └── evaluate.py
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_reconciliation.py
│   ├── test_tools.py
│   └── test_workflow.py
│
└── docs/
    └── architecture.md
```

---

## Dataset

The project uses four CSV files.

### Invoices

The invoice dataset contains fields such as:

```text
invoice_id
vendor_id
vendor_name
invoice_date
due_date
currency
subtotal
tax_amount
total_amount
po_number
cost_center
description
invoice_status
```

For reconciliation, the important fields are standardized into:

```text
invoice_id
vendor
date
amount
currency
reference
```

---

### Ledger Entries

The ledger dataset contains fields such as:

```text
ledger_entry_id
invoice_id
vendor_id
vendor_name
posting_date
transaction_type
amount
currency
reference
gl_account
cost_center
description
status
```

---

### Bank Transactions

The bank dataset contains fields such as:

```text
transaction_id
transaction_date
direction
amount
currency
counterparty_name
counterparty_account
reference
payment_method
bank_account
description
```

---

### Reconciliation Ground Truth

The ground-truth dataset is used only for evaluation.

It contains:

```text
invoice_id
scenario
expected_action
ledger_entry_ids
bank_transaction_ids
```

The ground-truth file must not be used as input to the reconciliation agent.

---

## Ingestion Layer

The ingestion layer is responsible for loading, validating, and cleaning the financial data.

### `loader.py`

The loader:

* Reads CSV files.
* Calls the validation logic.
* Renames different dataset columns into common names.
* Converts dates into datetime values.
* Converts amounts into numeric values.
* Standardizes currency values.
* Removes unnecessary whitespace.

After cleaning, the three main datasets use common fields:

```text
vendor
date
amount
currency
reference
```

### `validators.py`

The validator checks:

* Required columns.
* Missing primary keys.
* Duplicate IDs.
* Invalid amounts.
* Invalid dates.
* Ground-truth structure.

---

## Reconciliation Layer

The reconciliation layer contains the main financial matching logic.

The reconciliation system detects scenarios such as:

* Exact match
* Vendor name variation
* Date shift
* Amount mismatch
* Duplicate payment
* Split payment
* Missing ledger entry
* Missing bank payment
* Unpaid invoice
* Bank fee
* Bank-only transaction

The main reconciliation flow is:

```text
Invoice
   |
   +--> Find related ledger entries
   |
   +--> Find related bank transactions
   |
   v
Compare references
Compare amounts
Compare dates
Compare currencies
Compare vendor names
   |
   v
Detect reconciliation scenario
   |
   v
Generate action
```

---

## Deterministic-First Design

The project follows a deterministic-first approach.

Normal Python logic is used for:

```text
Amount comparison
Date comparison
Reference matching
Currency comparison
Duplicate detection
Split-payment detection
Missing-record detection
```

The LLM should not perform financial calculations that normal code can perform reliably.

The LLM is mainly used for:

```text
Ambiguous cases
Evidence interpretation
Explanation generation
Recommendation generation
Investigation support
```

This improves reliability and auditability.

---

## Tools Layer

The tools layer connects the reconciliation logic to the LangGraph agent.

The agent should call controlled functions instead of directly performing financial calculations.

Example tools include:

```text
get_invoice()
get_ledger_entry()
search_transactions()
find_candidate_matches()
calculate_amount_difference()
check_duplicate_payment()
check_split_payment()
save_reconciliation_result()
create_exception_report()
```

---

## LangGraph Agent

LangGraph is used to manage the workflow.

### State

`state.py` stores the information shared between graph nodes.

Example fields:

```text
case_id
invoice
ledger_entry
transaction
candidate_matches
match_confidence
anomaly_types
evidence
investigation_notes
recommendation
needs_human_review
approved
final_status
```

### Nodes

`nodes.py` contains the workflow steps.

Example nodes:

```text
intake
matcher
anomaly_checker
investigator
resolver
human_review
finalizer
```

### Workflow

`workflow.py` connects the nodes.

Example:

```text
START
  |
  v
intake
  |
  v
matcher
  |
  v
anomaly_checker
  |
  +-------------------+
  |                   |
  v                   v
resolver          investigator
  |                   |
  +---------+---------+
            |
            v
       human_review
            |
            v
        finalizer
            |
            v
           END
```

---

## Human-in-the-Loop Review

Not every case should be automatically reconciled.

Cases with low confidence or important anomalies should be reviewed by a human.

Possible reviewer decisions:

```text
approve
reject
request_more_evidence
```

The workflow can pause and continue after the reviewer makes a decision.

---

## Database Layer

PostgreSQL is used to store the project data.

The database can contain:

```text
invoices
ledger_entries
bank_transactions
reconciliation_cases
candidate_matches
tool_events
human_reviews
audit_log
```

The database layer is separated into:

```text
connection.py
models.py
repository.py
```

---

## Service Layer

`reconciliation_service.py` coordinates the main system workflow.

It connects:

```text
Ingestion
Reconciliation
Agent
Database
```

The API should call the service layer instead of directly calling low-level reconciliation functions.

---

## API

FastAPI is used to expose the system through REST endpoints.

Possible endpoints:

```text
POST /reconcile
GET  /cases
GET  /cases/{case_id}
POST /cases/{case_id}/approve
POST /cases/{case_id}/reject
```

---

## Dashboard

Streamlit is used to build the human-review dashboard.

The dashboard can display:

* Invoice details
* Ledger details
* Bank transaction details
* Match confidence
* Detected anomalies
* Candidate matches
* Evidence
* Investigation notes
* Recommendation
* Approve and reject actions

---

## Evaluation

The project uses the ground-truth dataset to measure reconciliation quality.

Possible evaluation metrics include:

```text
Reconciliation accuracy
Auto-reconciliation precision
Exception recall
Candidate match accuracy
Human-review rate
Tool success rate
Workflow latency
```

For financial reconciliation, auto-reconciliation precision is especially important because incorrect automatic decisions can be risky.

---

## Technology Stack

| Area                  | Technology                            |
| --------------------- | ------------------------------------- |
| Programming Language  | Python                                |
| Data Processing       | Pandas                                |
| Matching              | RapidFuzz / Python similarity methods |
| Agent Workflow        | LangGraph                             |
| LLM Integration       | LangChain                             |
| Database              | PostgreSQL                            |
| ORM                   | SQLAlchemy                            |
| API                   | FastAPI                               |
| Dashboard             | Streamlit                             |
| Environment Variables | python-dotenv                         |
| Containerization      | Docker                                |
| Observability         | LangSmith                             |
| Version Control       | Git / GitHub                          |

---

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd agentic-financial-reconciliation
```

Create the virtual environment with `uv`:

```bash
uv venv .venv
```

Activate it on Linux:

```bash
source .venv/bin/activate
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies with `uv`:

```bash
uv pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` file from `.env.example`.

Example:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/reconciliation_db

LLM_API_KEY=your_api_key

LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=financial-reconciliation
```

Do not upload real API keys or passwords to GitHub.

---

## Running the Ingestion Layer

Example:

```python
from src.ingestion.loader import load_financial_data

invoices, ledger_entries, bank_transactions = load_financial_data()

print(invoices.head())
print(ledger_entries.head())
print(bank_transactions.head())
```

---

## Running Reconciliation

Example:

```python
from src.ingestion.loader import load_financial_data
from src.reconciliation.reconciliation import reconcile_all

invoices, ledger_entries, bank_transactions = load_financial_data()

results = reconcile_all(
    invoices,
    ledger_entries,
    bank_transactions,
)

print(results.head())
```

---

## Security Principles

The project follows several safety principles:

* The LLM does not directly modify accounting records.
* The LLM does not initiate real payments.
* Financial calculations are performed using deterministic Python logic.
* High-risk cases require human review.
* Ground truth is kept separate from agent input.
* Secrets are stored using environment variables.
* Reconciliation decisions should be auditable.
* Human-review decisions should be recorded.

---

## Current Scope

The current project focuses on:

* CSV-based financial data
* Supplier invoices
* Ledger entries
* Bank transactions
* Deterministic reconciliation
* Anomaly detection
* LangGraph workflow
* Human review
* PostgreSQL
* FastAPI
* Streamlit
* Evaluation
* Docker

The goal is to keep the system simple, understandable, and reliable.

---

## Future Work

Future improvements may include:

* Add Excel and PDF invoice support.
* Add OCR for scanned invoices.
* Integrate with real banking and ERP systems.
* Improve fuzzy vendor matching.
* Add machine-learning-based match scoring.
* Improve LLM investigation and explanation.
* Add persistent LangGraph checkpoints.
* Add role-based access control.
* Improve the human-review dashboard.
* Deploy the system to the cloud with monitoring and CI/CD.

---

## Design Principles

The project follows these main principles:

```text
Deterministic first
LLM only when useful
Human review for risky cases
Structured and auditable decisions
Simple architecture before unnecessary complexity
```

---

## Project Status

Development flow:

```text
Ingestion
   ↓
Reconciliation
   ↓
Tools
   ↓
LangGraph Agent
   ↓
Database
   ↓
API
   ↓
Dashboard
   ↓
Evaluation
   ↓
Docker
   ↓
Documentation
```

---

## Author

Chanupa

BSc (Hons) Information Technology
AI / ML and Agentic AI Portfolio Project
