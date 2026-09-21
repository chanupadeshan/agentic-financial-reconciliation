import pandas as pd 
import pytest
from src.ingestion.loader import (clean_dataframe, load_csv_to_dataframe)
from src.ingestion.validators import validate_dataframe



## 1. test valid invloices data
def test_validate_valid_invoices():
    df = pd.DataFrame(
        [
            {
                "invoice_id":"INV-001",
                "vendor_name":"ABC Company",
                "invoice_date":"2026-01-01",
                "currency":"USD",
                "total_amount":1000.0,
            }
        ]
    )

    validate_dataframe(df,"invoices")

## 2. test missing required column
def test_validate_missing_required_column():
    df = pd.DataFrame(
        [
            {
                "invoice_id": "INV-001",
                "vendor_name": "ABC Company",
                "invoice_date": "2026-01-01",
                "currency": "USD",
            },
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        validate_dataframe(df,"invoices")

## 3. test duplicate invoice_id
def test_validate_duplicate_invoice_id():
    df = pd.DataFrame(
        [
            {
                "invoice_id": "INV-001",
                "vendor_name": "ABC Company",
                "invoice_date": "2026-01-01",
                "currency": "USD",
                "total_amount": 1000.0,
            },
            {
                "invoice_id": "INV-001",
                "vendor_name": "XYZ Company",
                "invoice_date": "2026-01-02",
                "currency": "USD",
                "total_amount": 2000.0,
            },
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        validate_dataframe(df,"invoices")

## 4. test invalid amount
def test_invalid_amount():
    df = pd.DataFrame(
        [
            {
                "invoice_id": "INV-001",
                "vendor_name": "ABC Company",
                "invoice_date": "2026-01-01",
                "currency": "USD",
                "total_amount": "invalid_amount",
            }
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        validate_dataframe(df,"invoices")

## 5. test invalid date
def test_invalid_date():
    df = pd.DataFrame(
        [
            {
                "invoice_id": "INV-001",
                "vendor_name": "ABC Company",
                "invoice_date": "invalid_date",
                "currency": "USD",
                "total_amount": 1000.0,
            }
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        validate_dataframe(df,"invoices")

## 6. test invoice cleaning
def test_clean_invoices():
    df = pd.DataFrame(
        [
            {
                "invoice_id": "INV-001",
                "vendor_name": " ABC Company ",
                "invoice_date": "2026-01-01",
                "currency": "usd",
                "total_amount": 1000.0,
            }
        ]
    )

    cleaned_df = clean_dataframe(df,"invoices")

    ## assert : check that the result is what we expect
    ## example : The vendor name should be stripped of leading and trailing whitespace
    assert cleaned_df["vendor"].iloc[0] == "ABC Company"
    assert cleaned_df["date"].iloc[0] == pd.Timestamp("2026-01-01")
    assert cleaned_df["amount"].iloc[0] == 1000.0
    assert cleaned_df["currency"].iloc[0] == "USD"
    assert cleaned_df["reference"].iloc[0] == "INV-001"

## 7. test loading CSV files
def test_load_csv_to_dataframe(tmp_path):
    df = pd.DataFrame(
        [
            {
                "invoice_id": "INV-001",
                "vendor_name": "ABC Company",
                "invoice_date": "2026-01-01",
                "currency": "USD",
                "total_amount": 1000,
            }
        ]
    )

    file_path = tmp_path / "invoices.csv"
    df.to_csv(file_path, index=False)

    loaded_df = load_csv_to_dataframe(file_path, "invoices")

    assert loaded_df.shape[0] == 1
    assert loaded_df["invoice_id"].iloc[0] == "INV-001"
    assert loaded_df["vendor"].iloc[0] == "ABC Company"
    assert loaded_df["date"].iloc[0] == pd.Timestamp("2026-01-01")
    assert loaded_df["currency"].iloc[0] == "USD"
    assert loaded_df["amount"].iloc[0] == 1000