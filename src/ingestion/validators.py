import pandas as pd

REQUIRED_COLUMNS = {
    "invoices":
    [
        "invoice_id",
        "vendor_name",
        "invoice_date",
        "currency",
        "total_amount",
    ],
    "ledger_entries":
    [
        "ledger_entry_id",
        "invoice_id",
        "vendor_id",
        "vendor_name",
        "posting_date",
        "amount",
        "currency",
        "reference",
    ],
    "bank_transactions":
    [
        "transaction_id",
        "transaction_date",
        "amount",
        "currency",
        "counterparty_name",
        "reference",
    ],
    "ground_truth":
    [
        "invoice_id",
        "scenario",
        "expected_action",
        "ledger_entry_ids",
        "bank_transaction_ids",
    ],
}


primary_keys = {
    "invoices":"invoice_id",
    "ledger_entries":"ledger_entry_id",
    "bank_transactions":"transaction_id",
}

def validate_dataframe(df:pd.DataFrame,table_name:str)->None:
    """
        Validate one project CSV before it is used.
        Raises ValueError if important data is invalid.
    """

    if table_name not in REQUIRED_COLUMNS:
        raise ValueError(f'Unknown table name: {table_name}')
    
    ##check required columns
    missing_columns = [
        col for col in REQUIRED_COLUMNS[table_name] if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(f'Missing required columns for {table_name}: {missing_columns}')

    
    if table_name == "ground_truth":
        if df["scenario"].isnull().any():
            raise ValueError("Ground truth data contains null values in 'scenario' column.")
        
        if df["expected_action"].isnull().any():
            raise ValueError("Ground truth data contains null values in 'expected_action' column.")

        has_record = (
            df["invoice_id"].notna() | df["ledger_entry_ids"].notna() | df["bank_transaction_ids"].notna()
        )

        if not has_record.all():
            raise ValueError("Ground truth data contains rows without any record identifiers (invoice_id, ledger_entry_ids, bank_transaction_ids).")

        
        return

    ##check primary key 
    id_column = primary_keys[table_name]

    if df[id_column].isna().any():
        raise ValueError(f"{table_name} data contains null values in primary key column '{id_column}'.")

    if df[id_column].astype(str).duplicated().any():
        raise ValueError(f"{table_name} data contains duplicate values in primary key column '{id_column}'.")

    ## check amount
    ## because the amount column name differs for invoices, we need to handle it separately invoices have "total_amount" while others have "amount"
    amount_column = "total_amount" if table_name == "invoices" else "amount"
    amount = pd.to_numeric((df[amount_column]), errors="coerce")

    if amount.isna().any():
        raise ValueError(f"{table_name} data contains non-numeric values in amount column '{amount_column}'.")

    ## check date
    date_column = {
        "invoices":"invoice_date",
        "ledger_entries":"posting_date",
        "bank_transactions":"transaction_date",
    }[table_name]

    dates = pd.to_datetime(df[date_column], errors="coerce")

    if dates.isna().any():
        raise ValueError(f"{table_name} data contains invalid date values in date column '{date_column}'.")
    