"""
prepare_deployment.py
─────────────────────
Generates the pre-computed CSV files that Streamlit Cloud loads instead of
querying the database live (the DB is not accessible from Streamlit Cloud).

Run this locally whenever the source data changes, then commit and push:

    python prepare_deployment.py
    git add dashboards/inventory_policy.csv dashboards/forecast_data.csv dashboards/actuals_data.csv
    git push

Output files (committed to git):
    dashboards/inventory_policy.csv  — safety stock & ROP per category (from inventory_optimization.py)
    dashboards/actuals_data.csv      — historical daily demand per category (top N)
    dashboards/forecast_data.csv     — Prophet forecast (ds, yhat, yhat_lower, yhat_upper) per category
"""

import os
import warnings
import pandas as pd
from sqlalchemy import text

warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from config import get_engine, OUTPUT_DIR

TOP_N         = 5
FORECAST_DAYS = 90


# ─────────────────────────────────────────────────────────────────────────────

def load_top_categories(n: int) -> list[str]:
    engine = get_engine()
    sql = text("""
        SELECT category_name, SUM(order_item_quantity) AS total_qty
        FROM orders
        WHERE category_name IS NOT NULL AND order_item_quantity IS NOT NULL
        GROUP BY category_name
        ORDER BY total_qty DESC
        LIMIT :n
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"n": n})
    return df["category_name"].tolist()


def load_daily_demand(category: str) -> pd.DataFrame:
    engine = get_engine()
    sql = text("""
        SELECT
            DATE(STR_TO_DATE(order_date_dateorders, '%m/%d/%Y %H:%i')) AS ds,
            SUM(order_item_quantity) AS y
        FROM orders
        WHERE category_name = :cat
          AND order_status NOT IN ('CANCELED', 'SUSPECTED_FRAUD')
          AND order_date_dateorders IS NOT NULL
        GROUP BY ds
        ORDER BY ds
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"cat": category})
    df["ds"] = pd.to_datetime(df["ds"])
    return df.dropna().query("y > 0").reset_index(drop=True)


def run_prophet(df: pd.DataFrame) -> pd.DataFrame:
    from prophet import Prophet
    span = (df["ds"].max() - df["ds"].min()).days
    model = Prophet(
        yearly_seasonality=span >= 365,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=0.95,
        changepoint_prior_scale=0.1,
    )
    model.fit(df)
    future = model.make_future_dataframe(periods=FORECAST_DAYS, freq="D")
    return model.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]]


# ─────────────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Check inventory_policy.csv exists ────────────────────────────────────
    policy_path = os.path.join(OUTPUT_DIR, "inventory_policy.csv")
    if not os.path.exists(policy_path):
        print("inventory_policy.csv not found — run `python inventory_optimization.py` first.")
        return

    # ── Build forecast & actuals CSVs ────────────────────────────────────────
    categories = load_top_categories(TOP_N)
    print(f"Generating forecast data for top {TOP_N} categories:")

    all_actuals   = []
    all_forecasts = []

    for cat in categories:
        print(f"  [{cat}] loading demand...", end=" ", flush=True)
        df_actual = load_daily_demand(cat)

        print("fitting Prophet...", end=" ", flush=True)
        forecast = run_prophet(df_actual)

        actuals_row = df_actual.copy()
        actuals_row["category"] = cat
        all_actuals.append(actuals_row)

        fc_row = forecast.copy()
        fc_row["category"] = cat
        all_forecasts.append(fc_row)

        print("done")

    actuals_df  = pd.concat(all_actuals,   ignore_index=True)
    forecast_df = pd.concat(all_forecasts, ignore_index=True)

    actuals_path  = os.path.join(OUTPUT_DIR, "actuals_data.csv")
    forecast_path = os.path.join(OUTPUT_DIR, "forecast_data.csv")

    actuals_df.to_csv(actuals_path,  index=False)
    forecast_df.to_csv(forecast_path, index=False)

    print(f"\nSaved:")
    print(f"  {actuals_path}   ({len(actuals_df):,} rows)")
    print(f"  {forecast_path}  ({len(forecast_df):,} rows)")
    print(f"  {policy_path}    (unchanged)")
    print("\nAll deployment CSVs ready.")
    print("Next: git add dashboards/inventory_policy.csv dashboards/forecast_data.csv dashboards/actuals_data.csv && git push")


if __name__ == "__main__":
    main()
