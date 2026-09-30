# Running the Project

## 1. What runs today

The project's current application is the Streamlit dashboard in `dashboard/app.py`. It lets you:

1. upload invoice, ledger, and bank CSV files;
2. run deterministic reconciliation;
3. inspect results and anomalies;
4. investigate anomaly cases with the Groq-hosted AI model;
5. approve or reject cases; and
6. export results.

The FastAPI and evaluation entry points are currently placeholders, so there is no API server or evaluation command to start yet.

## 2. Prerequisites

Install:

- Python 3.12;
- `uv` or `pip`;
- a Groq API key for AI investigation; and
- Docker only if you want to run the containerized version.

Run all commands from the repository root:

```bash
cd "/path/to/Agentic Financial Reconciliation and Audit Copilot"
```

## 3. Local installation

### Option A: using `uv`

Create and activate a virtual environment:

```bash
uv venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
uv venv .venv
.venv\Scripts\Activate.ps1
```

Install the dependencies:

```bash
uv pip install -r requirements.txt
```

### Option B: using standard Python and pip

On Linux or macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 4. Environment configuration

Create a `.env` file in the repository root. The checked-in `.env.example` is currently only a placeholder, so add these values manually:

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
```

`GROQ_MODEL` is optional; `openai/gpt-oss-120b` is the code's default.

Optional LangSmith tracing variables can also be supplied:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=financial-reconciliation
```

Do not commit `.env` or expose real API keys. The dashboard imports the agent module at startup, and that module constructs the Groq client, so a valid `GROQ_API_KEY` should be configured even before clicking “Investigate with AI.”

## 5. Start the dashboard

With the virtual environment activated, run:

```bash
python -m streamlit run dashboard/app.py \
  --server.address=0.0.0.0 \
  --server.port=8503
```

Open:

```text
http://localhost:8503
```

Stop the server with `Ctrl+C`.

## 6. Run a reconciliation in the UI

Open the **Upload Data** tab and upload:

| Dashboard field | Bundled example file |
|---|---|
| Invoices CSV | `data/raw/invoices.csv` |
| Ledger Entries CSV | `data/raw/ledger_entries.csv` |
| Bank Transactions CSV | `data/raw/bank_transactions.csv` |

Then:

1. Optionally expand **Preview uploaded data**.
2. Click **Run Reconciliation**.
3. Use **Overview** to inspect totals and scenario counts.
4. Use **Review Cases** to inspect anomaly evidence.
5. Open **Investigation & Review**, select a pending case, and click **Investigate with AI**.
6. Review the AI-generated evidence summary and recommendation.
7. Enter the reviewer name/comment and select **Approve** or **Reject**.
8. Use **Decision History** and **Export** as needed.

The deterministic reconciliation itself does not call AI. AI runs only when **Investigate with AI** is selected for an anomaly case.

Review decisions, uploaded data, AI results, and LangGraph checkpoints are held in memory. Restarting the application or losing the Streamlit session removes that state.

## 7. Run with Docker

Build the image from the repository root:

```bash
docker build -t financial-reconciliation-copilot .
```

Run it with the environment file and expose the dashboard:

```bash
docker run --rm \
  --name financial-reconciliation-copilot \
  --env-file .env \
  -p 8503:8503 \
  financial-reconciliation-copilot
```

Open `http://localhost:8503`, then upload the three CSV files through the dashboard.

Stop the foreground container with `Ctrl+C`. If it was started in detached mode, stop it with:

```bash
docker stop financial-reconciliation-copilot
```

The current repository should be run with the Dockerfile directly; a working Docker Compose configuration is not part of the current project state.

## 8. Run reconciliation directly from Python

The deterministic engine can be used without the dashboard or AI:

```python
from src.ingestion.loader import load_financial_data
from src.reconciliation.reconciliation import reconcile_all_invoices

invoices, ledger_entries, bank_transactions = load_financial_data(
    "data/raw"
)

results = reconcile_all_invoices(
    invoices,
    ledger_entries,
    bank_transactions,
)

print(results.head())
print(results["scenario"].value_counts())
```

Save that example as a script in the repository root and run it with the activated virtual environment:

```bash
python your_script.py
```

Passing `"data/raw"` explicitly is important when running from the repository root because the loader's current default path is `../data/raw`.

## 9. Run the tests

The normal command from an activated environment is:

```bash
python -m pytest -q
```

In an environment that auto-loads incompatible system pytest plugins, use the verified isolated command on Linux or macOS:

```bash
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  .venv/bin/python -m pytest -q
```

PowerShell equivalent:

```powershell
$env:PYTHONPATH = "."
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
.venv\Scripts\python.exe -m pytest -q
```

At the time this runbook was written, the isolated command completes with:

```text
57 passed
```

## 10. Common problems

### `ModuleNotFoundError: No module named 'src'`

Run the command from the repository root and prefer:

```bash
PYTHONPATH=. python -m pytest -q
```

For the application, use `python -m streamlit ...` from the repository root.

### Groq authentication or model error

Check that:

- `.env` is in the repository root;
- `GROQ_API_KEY` contains a valid key;
- `GROQ_MODEL` names a model available to the account; and
- the machine/container has network access.

Deterministic reconciliation does not need a model response, but the current dashboard imports and initializes the Groq client during application startup.

### CSV missing-column error

Use the bundled files first and preserve their headers. Required formats are documented in `docs/csv_files_guide.md`.

### Port 8503 is already in use

Choose another local port:

```bash
python -m streamlit run dashboard/app.py --server.port=8504
```

Then open `http://localhost:8504`.

For Docker, map a different host port while leaving the container port unchanged:

```bash
docker run --rm --env-file .env -p 8504:8503 \
  financial-reconciliation-copilot
```

### No persistent review history

This is expected in the current architecture. PostgreSQL persistence and an audit repository are described as future work but are not implemented.
