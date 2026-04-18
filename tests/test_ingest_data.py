"""
Unit tests for ingest_data.py

Covers:
  - validate_source: raises on missing required columns
  - validate_source: raises on negative quantities
  - validate_source: raises on negative lead times
  - clean_data: coerces non-numeric to NaN without dropping rows
  - clean_columns: normalises column names correctly
"""

import pytest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ingest_data import validate_source, clean_data, clean_columns, REQUIRED_COLUMNS


def _base_df() -> pd.DataFrame:
    """Minimal valid dataframe satisfying REQUIRED_COLUMNS."""
    return pd.DataFrame([{
        "order_item_quantity":        10,
        "order_date_dateorders":      "1/15/2018 0:00",
        "category_name":              "Cleats",
        "days_for_shipping_real":     3,
        "days_for_shipment_scheduled": 4,
        "order_status":               "COMPLETE",
        "sales":                      99.99,
        "order_profit_per_order":     15.0,
    }])


# ── validate_source ───────────────────────────────────────────────────────────

def test_validate_source_passes_valid_df():
    validate_source(_base_df())  # must not raise


def test_validate_source_raises_on_missing_column():
    df = _base_df().drop(columns=["category_name"])
    with pytest.raises(ValueError, match="missing required columns"):
        validate_source(df)


def test_validate_source_raises_on_negative_quantity():
    df = _base_df()
    df["order_item_quantity"] = -1
    with pytest.raises(ValueError, match="negative values"):
        validate_source(df)


def test_validate_source_raises_on_negative_lead_time():
    df = _base_df()
    df["days_for_shipping_real"] = -2
    with pytest.raises(ValueError, match="negative values"):
        validate_source(df)


# ── clean_data ────────────────────────────────────────────────────────────────

def test_clean_data_coerces_non_numeric_to_nan():
    df = _base_df().copy()
    df["order_item_quantity"] = "bad_value"
    result = clean_data(df)
    assert pd.isna(result["order_item_quantity"].iloc[0])
    assert len(result) == 1  # row must not be dropped


def test_clean_data_strips_whitespace():
    df = _base_df().copy()
    df["category_name"] = "  Cleats  "
    result = clean_data(df)
    assert result["category_name"].iloc[0] == "Cleats"


# ── clean_columns ─────────────────────────────────────────────────────────────

def test_clean_columns_lowercases_and_replaces_spaces():
    df = pd.DataFrame(columns=["Order ID", "Category Name", "Sales$"])
    result = clean_columns(df)
    # trailing underscores are stripped, so "Sales$" → "sales"
    assert list(result.columns) == ["order_id", "category_name", "sales"]


def test_clean_columns_collapses_consecutive_underscores():
    df = pd.DataFrame(columns=["Order  ID"])
    result = clean_columns(df)
    assert result.columns[0] == "order_id"
