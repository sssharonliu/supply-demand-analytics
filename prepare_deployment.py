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

warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from config import (get_engine, OUTPUT_DIR, DEPLOY_TOP_N, FORECAST_DAYS,
                    PROPHET_INTERVAL_WIDTH, PROPHET_CHANGEPOINT_PRIOR)
from data import fetch_daily_demand, fetch_top_categories


def run_prophet(engine, category: str) -> pd.DataFrame:
    from prophet import Prophet
    df = fetch_daily_demand(engine, category)
    span = (df["ds"].max() - df["ds"].min()).days
    model = Prophet(
        yearly_seasonality=span >= 365,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=PROPHET_INTERVAL_WIDTH,
        changepoint_prior_scale=PROPHET_CHANGEPOINT_PRIOR,
    )
    model.fit(df)
    future = model.make_future_dataframe(periods=FORECAST_DAYS, freq="D")
    return df, model.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]]


# ─────────────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Check inventory_policy.csv exists ────────────────────────────────────
    policy_path = os.path.join(OUTPUT_DIR, "inventory_policy.csv")
    if not os.path.exists(policy_path):
        print("inventory_policy.csv not found — run `python inventory_optimization.py` first.")
        return

    engine = get_engine()

    # ── Build forecast & actuals CSVs ────────────────────────────────────────
    categories = fetch_top_categories(engine, DEPLOY_TOP_N)
    print(f"Generating forecast data for top {DEPLOY_TOP_N} categories:")

    all_actuals   = []
    all_forecasts = []

    for cat in categories:
        print(f"  [{cat}] loading demand + fitting Prophet...", end=" ", flush=True)
        df_actual, forecast = run_prophet(engine, cat)

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
    print(f"  {policy_path}    (unchanged — re-run inventory_optimization.py to refresh)")
    print("\nAll deployment CSVs ready.")
    print("Next: git add dashboards/inventory_policy.csv dashboards/forecast_data.csv dashboards/actuals_data.csv && git push")


if __name__ == "__main__":
    main()
