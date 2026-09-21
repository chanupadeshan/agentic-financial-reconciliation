from pathlib import Path
import pandas as pd 
from .validators import validate_dataframe


def clean_dataframe(df:pd.DataFrame,table_name:str)->pd.DataFrame:
    """
    Clean the real project CSV columns and convert them to common reconciliation column names.
    """

    df = df.copy()
    if table_name == "invoices":
        df=df.rename(
            columns={
                "vendor_name": "vendor",
                "invoice_date": "date",
                "total_amount": "amount",
            }
        )

        ## Invoice ID become the reconciliation reference
        df["reference"] = df["invoice_id"]

    elif table_name == "ledger_entries":
        df=df.rename(
            columns={
                "vendor_name":"vendor",
                "posting_date":"date",
            }
        )

    elif table_name == "bank_transactions":
        df=df.rename(
            columns={
                "counterparty_name":"vendor",
                "transaction_date":"date",
            }
        )

    elif table_name == "ground_truth":
        ## evaluation data stays unchanged
        return df 
    
    else:
        raise ValueError(f"Unknown table name: {table_name}")

    ## common cleaning for reconciliation tables
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["currency"] = df["currency"].str.upper()

    for col in ["vendor","currency","reference"]:
        df[col] = df[col].str.strip().astype("string")

    return df

def load_csv_to_dataframe(file_path:Path,table_name:str)->pd.DataFrame:
    """
    Load one CSV file, validate it, and clean it.
    """
    
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_csv(file_path)
    validate_dataframe(df,table_name)

    return clean_dataframe(df,table_name)

def load_financial_data(data_dir="../data/raw",):
    """
        Load only the three operational datasets.
        Ground truth is intentionally excluded.
    """

    data_dir = Path(data_dir)

    invoices_df = load_csv_to_dataframe(data_dir / "invoices.csv","invoices")
    ledger_entries_df = load_csv_to_dataframe(data_dir / "ledger_entries.csv","ledger_entries")
    bank_transactions_df = load_csv_to_dataframe(data_dir / "bank_transactions.csv","bank_transactions")

    return invoices_df, ledger_entries_df, bank_transactions_df

def load_ground_truth(data_dir="../data/raw",):
    """
        Load only the ground truth dataset.
    """

    data_dir = Path(data_dir)

    ground_truth_df = load_csv_to_dataframe(data_dir / "ground_truth.csv","ground_truth")

    return ground_truth_df
    
    