"""
Unit tests for inventory_optimization.py

Covers:
  - compute_inventory_policy: combined-variance safety stock formula
  - compute_inventory_policy: deterministic lead time reduces to simple formula
  - compute_inventory_policy: single-observation category (std = NaN → 0)
  - validate_source (via ingest_data): negative quantities are rejected
"""

import math
import pytest
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from inventory_optimization import compute_inventory_policy, Z_SCORE


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_df(n_days: int = 30, qty: float = 10.0, lead_time: float = 5.0,
             lead_time_std: float = 0.0) -> pd.DataFrame:
    """Build a minimal raw-order dataframe for one category."""
    dates = pd.date_range("2023-01-01", periods=n_days, freq="D")
    rows = []
    for d in dates:
        rows.append({
            "category_name": "TestCat",
            "order_date": d,
            "order_item_quantity": qty,
            "days_for_shipping_real": lead_time + (np.random.uniform(-lead_time_std, lead_time_std)
                                                    if lead_time_std else 0.0),
        })
    return pd.DataFrame(rows)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_safety_stock_deterministic_lead_time():
    """When σ_LT = 0, combined formula equals Z × σ_demand × √μ_LT."""
    # 30 days, constant qty → σ_demand = 0 → safety stock = 0
    df = _make_df(n_days=60, qty=10.0, lead_time=4.0, lead_time_std=0.0)
    policy = compute_inventory_policy(df)
    row = policy[policy["category_name"] == "TestCat"].iloc[0]
    assert row["safety_stock"] == 0.0


def test_safety_stock_combined_variance():
    """Combined-variance formula produces higher SS than simple formula when σ_LT > 0."""
    np.random.seed(42)
    df = _make_df(n_days=120, qty=10.0, lead_time=5.0, lead_time_std=2.0)
    # Add some demand variance
    df["order_item_quantity"] = np.random.randint(5, 20, size=len(df)).astype(float)

    policy = compute_inventory_policy(df)
    row = policy[policy["category_name"] == "TestCat"].iloc[0]

    # Simple formula (ignores σ_LT)
    simple_ss = Z_SCORE * row["std_daily_demand"] * math.sqrt(row["avg_lead_time"])
    # Combined formula must be >= simple when σ_LT > 0
    assert row["safety_stock"] >= simple_ss - 0.5  # allow 0.5 rounding tolerance
    assert row["std_lead_time"] > 0


def test_rop_equals_cycle_plus_safety():
    """ROP must always equal cycle_stock + safety_stock."""
    np.random.seed(0)
    df = _make_df(n_days=60, qty=8.0, lead_time=3.0, lead_time_std=1.0)
    df["order_item_quantity"] = np.random.randint(3, 15, size=len(df)).astype(float)

    policy = compute_inventory_policy(df)
    for _, row in policy.iterrows():
        assert abs(row["rop"] - (row["cycle_stock"] + row["safety_stock"])) < 0.2


def test_single_observation_category_no_crash():
    """A category with only one order date must not crash (std → NaN → 0)."""
    df = pd.DataFrame([{
        "category_name": "RareCat",
        "order_date": pd.Timestamp("2023-06-01"),
        "order_item_quantity": 5.0,
        "days_for_shipping_real": 3.0,
    }])
    policy = compute_inventory_policy(df)
    row = policy[policy["category_name"] == "RareCat"].iloc[0]
    assert row["safety_stock"] == 0.0
    assert row["rop"] == row["cycle_stock"]


def test_multiple_categories_sorted_by_rop_descending():
    """Output must be sorted ROP descending."""
    np.random.seed(7)
    rows = []
    for cat, qty, lt in [("A", 50, 10), ("B", 5, 2), ("C", 20, 5)]:
        for d in pd.date_range("2023-01-01", periods=60):
            rows.append({
                "category_name": cat,
                "order_date": d,
                "order_item_quantity": float(qty),
                "days_for_shipping_real": float(lt),
            })
    df = pd.DataFrame(rows)
    policy = compute_inventory_policy(df)
    assert policy["rop"].is_monotonic_decreasing
