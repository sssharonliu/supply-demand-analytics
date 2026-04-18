"""
inventory_optimization.py
──────────────────────────
Phase 2 — Inventory Policy Engine
Calculates Safety Stock and Reorder Point (ROP) per product category
at a 95% service level using the combined-variance formula (Nahmias & Olsen):

    Safety Stock = Z × √(σ²_demand × μ_LT  +  μ²_demand × σ²_LT)
    ROP          = (μ_demand × μ_LT) + Safety Stock

    Z = 1.645  →  95% service level

The simple formula  Z × σ_demand × √(μ_LT)  assumes deterministic lead time.
This dataset has a 79.8% late-delivery rate, so σ_LT is material and must be
included to avoid systematically under-estimating safety stock.

Output
  dashboards/04_inventory_recommendations.png  — Top 10 ROP stacked bar chart
  Console table — Category · Daily Demand · Lead Time · Safety Stock · ROP
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from sqlalchemy import text

# ── Working directory ─────────────────────────────────────────────────────────
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import get_engine, OUTPUT_DIR, DB_NAME, CHART_TOP_N

# ── Configuration ─────────────────────────────────────────────────────────────
Z_SCORE = 1.645   # 95% one-tailed service level
TOP_N   = CHART_TOP_N

os.makedirs(OUTPUT_DIR, exist_ok=True)
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)


def fetch_raw_data(engine) -> pd.DataFrame:
    """
    Pull per-order rows with the three columns needed:
      category_name, order_date, order_item_quantity, days_for_shipping_real
    Excludes cancelled / fraud orders and rows with null critical fields.
    """
    sql = text("""
        SELECT
            category_name,
            DATE(STR_TO_DATE(order_date_dateorders, '%m/%d/%Y %H:%i')) AS order_date,
            order_item_quantity,
            days_for_shipping_real
        FROM orders
        WHERE order_status NOT IN ('CANCELED', 'SUSPECTED_FRAUD')
          AND category_name        IS NOT NULL
          AND order_item_quantity  IS NOT NULL
          AND days_for_shipping_real IS NOT NULL
          AND order_date_dateorders IS NOT NULL
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2. Inventory calculations
# ─────────────────────────────────────────────────────────────────────────────

def compute_inventory_policy(df: pd.DataFrame) -> pd.DataFrame:
    """
    1. Aggregate order_item_quantity to daily level per category.
    2. Calculate μ, σ of daily demand and average lead time per category.
    3. Apply Safety Stock and ROP formulas.
    Returns one row per category, sorted by ROP descending.
    """
    # ── Daily demand per category ─────────────────────────────────────────
    daily = (
        df.groupby(["category_name", "order_date"])["order_item_quantity"]
        .sum()
        .reset_index()
        .rename(columns={"order_item_quantity": "daily_qty"})
    )

    demand_stats = (
        daily.groupby("category_name")["daily_qty"]
        .agg(avg_daily_demand="mean", std_daily_demand="std")
        .reset_index()
    )

    # ── Lead time stats per category (mean + std) ────────────────────────
    lt_stats = (
        df.groupby("category_name")["days_for_shipping_real"]
        .agg(avg_lead_time="mean", std_lead_time="std")
        .reset_index()
    )

    # ── Merge ─────────────────────────────────────────────────────────────
    policy = demand_stats.merge(lt_stats, on="category_name")
    policy["std_daily_demand"] = policy["std_daily_demand"].fillna(0)
    policy["std_lead_time"]    = policy["std_lead_time"].fillna(0)

    # ── Combined-variance safety stock (Nahmias & Olsen) ─────────────────
    # Accounts for both demand variance during lead time AND lead-time variance.
    # Reduces to the simple formula when σ_LT = 0 (deterministic lead time).
    policy["safety_stock"] = (
        Z_SCORE * np.sqrt(
            policy["std_daily_demand"] ** 2 * policy["avg_lead_time"]
            + policy["avg_daily_demand"] ** 2 * policy["std_lead_time"] ** 2
        )
    ).round(1)

    policy["cycle_stock"] = (
        policy["avg_daily_demand"] * policy["avg_lead_time"]
    ).round(1)

    policy["rop"] = (policy["cycle_stock"] + policy["safety_stock"]).round(1)

    return policy.sort_values("rop", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Visualisation — Chart 04
# ─────────────────────────────────────────────────────────────────────────────

def plot_rop_chart(policy: pd.DataFrame) -> str:
    """
    Horizontal stacked bar chart — Top N categories by ROP.
      Base bar  : Cycle Stock  (μ × LT)        — steel blue
      Stack bar : Safety Stock (Z × σ × √LT)   — coral / salmon
    """
    top = policy.head(TOP_N).sort_values("rop", ascending=True)  # ascending for horizontal chart

    fig, ax = plt.subplots(figsize=(12, 7))

    cycle_color  = "#3a7ebf"   # steel blue
    safety_color = "#e07b6a"   # coral / salmon

    # Base: Cycle Stock
    bars_cycle = ax.barh(
        top["category_name"], top["cycle_stock"],
        color=cycle_color, edgecolor="white", linewidth=0.6,
        label=f"Cycle Stock  (μ × Lead Time)"
    )

    # Stack: Safety Stock
    bars_safety = ax.barh(
        top["category_name"], top["safety_stock"],
        left=top["cycle_stock"],
        color=safety_color, edgecolor="white", linewidth=0.6,
        label=f"Safety Stock  (Z={Z_SCORE} × √(σ²_d·μ_LT + μ²_d·σ²_LT))"
    )

    # ROP value labels at the end of each bar
    for _, row in top.iterrows():
        ax.text(
            row["rop"] + (top["rop"].max() * 0.008),
            row["category_name"],
            f"ROP: {row['rop']:,.0f}",
            va="center", ha="left", fontsize=8.5, color="#333333"
        )

    ax.set_xlabel("Units (inventory quantity)", labelpad=10)
    ax.set_title(
        f"Inventory Policy — Top {TOP_N} Categories by Reorder Point (ROP)\n"
        f"95% Service Level  ·  Z = {Z_SCORE}  ·  Safety Stock shown in coral",
        fontsize=13, fontweight="bold", pad=14
    )

    # Legend
    cycle_patch  = mpatches.Patch(color=cycle_color,  label="Cycle Stock  (μ × Lead Time)")
    safety_patch = mpatches.Patch(color=safety_color, label="Safety Stock  (Z × √(σ²_d·μ_LT + μ²_d·σ²_LT))")
    ax.legend(handles=[cycle_patch, safety_patch], loc="lower right", fontsize=9, framealpha=0.9)

    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xlim(0, top["rop"].max() * 1.18)

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, "04_inventory_recommendations.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# 4. Console report
# ─────────────────────────────────────────────────────────────────────────────

def export_policy_csv(policy: pd.DataFrame) -> str:
    """Save the full policy table to CSV for procurement teams."""
    out_path = os.path.join(OUTPUT_DIR, "inventory_policy.csv")
    policy[[
        "category_name", "avg_daily_demand", "std_daily_demand",
        "avg_lead_time", "std_lead_time", "safety_stock", "cycle_stock", "rop"
    ]].to_csv(out_path, index=False, float_format="%.2f")
    return out_path


def print_policy_table(policy: pd.DataFrame):
    top = policy.head(TOP_N)

    col_w = [28, 14, 12, 14, 12]
    headers = ["Category", "Avg Daily Demand", "Lead Time", "Safety Stock", "ROP"]
    divider = "─" * (sum(col_w) + len(col_w) * 2 + 1)

    print()
    print(divider)
    print(f"  INVENTORY POLICY RECOMMENDATIONS  (95% Service Level · Z = {Z_SCORE})")
    print(divider)
    header_row = (
        f"  {headers[0]:<{col_w[0]}}"
        f"  {headers[1]:>{col_w[1]}}"
        f"  {headers[2]:>{col_w[2]}}"
        f"  {headers[3]:>{col_w[3]}}"
        f"  {headers[4]:>{col_w[4]}}"
    )
    print(header_row)
    print(f"  {'':─<{col_w[0]}}  {'(units/day)':>{col_w[1]}}  {'(days)':>{col_w[2]}}  {'(units)':>{col_w[3]}}  {'(units)':>{col_w[4]}}")
    print(divider)

    for _, row in top.iterrows():
        print(
            f"  {row['category_name']:<{col_w[0]}}"
            f"  {row['avg_daily_demand']:>{col_w[1]}.1f}"
            f"  {row['avg_lead_time']:>{col_w[2]}.1f}"
            f"  {row['safety_stock']:>{col_w[3]}.1f}"
            f"  {row['rop']:>{col_w[4]}.1f}"
        )

    print(divider)
    print(f"  Total categories analysed: {len(policy)}")
    print()
    print("  SCA NOTE: ROP = trigger point to initiate replenishment.")
    print("  When on-hand inventory falls to ROP, place a purchase order.")
    print("  Safety Stock is the buffer against demand spikes and late deliveries.")
    print(divider)
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # ── Connect ───────────────────────────────────────────────────────────
    print("Connecting to database...")
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("  Connection successful.\n")
    except Exception as exc:
        print(f"  ERROR: Could not connect to database — {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Extract ───────────────────────────────────────────────────────────
    print("Extracting order data...")
    try:
        df = fetch_raw_data(engine)
        print(f"  {len(df):,} rows loaded across {df['category_name'].nunique()} categories.\n")
    except Exception as exc:
        print(f"  ERROR fetching data — {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Calculate policy ──────────────────────────────────────────────────
    print("Calculating Safety Stock and Reorder Points...")
    try:
        policy = compute_inventory_policy(df)
        print(f"  Policy computed for {len(policy)} categories.\n")
    except Exception as exc:
        print(f"  ERROR in policy calculation — {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Chart ─────────────────────────────────────────────────────────────
    print("Generating Chart 04 — Inventory Recommendations...")
    try:
        path = plot_rop_chart(policy)
        print(f"  Saved → {path}\n")
    except Exception as exc:
        print(f"  ERROR generating chart — {exc}", file=sys.stderr)

    # ── CSV export ────────────────────────────────────────────────────────
    print("Exporting policy table to CSV...")
    try:
        csv_path = export_policy_csv(policy)
        print(f"  Saved → {csv_path}\n")
    except Exception as exc:
        print(f"  ERROR exporting CSV — {exc}", file=sys.stderr)

    # ── Console table ─────────────────────────────────────────────────────
    print_policy_table(policy)


if __name__ == "__main__":
    main()
