"""
demand_forecasting.py
─────────────────────
Phase 2 — Time-Series Demand Forecasting
Uses Facebook Prophet to forecast the next 90 days of demand for the
highest-volume product category, surfacing worst-case (upper-bound)
demand as the planning input for safety stock and procurement.

Outputs
  dashboards/05_demand_forecast.png     — Actual vs. Predicted with CI
  dashboards/06_seasonality_analysis.png — Weekly & yearly seasonality components
"""

import os
import sys
import warnings
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sqlalchemy import text  # used by get_engine() health check in main()

warnings.filterwarnings("ignore")  # suppress Prophet/Stan verbosity

# ── Working directory ─────────────────────────────────────────────────────────
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import get_engine, OUTPUT_DIR, FORECAST_DAYS, PROPHET_INTERVAL_WIDTH, PROPHET_CHANGEPOINT_PRIOR
from data import fetch_daily_demand, fetch_top_categories

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Forecasting
# ─────────────────────────────────────────────────────────────────────────────

def build_and_run_model(df: pd.DataFrame) -> tuple:
    """
    Fit a Prophet model and return (model, forecast_df).
    Raises ImportError with a helpful message if Prophet is not installed.
    """
    try:
        from prophet import Prophet
    except ImportError:
        raise ImportError(
            "Prophet is not installed. Run: pip install prophet"
        )

    data_span_days = (df["ds"].max() - df["ds"].min()).days
    use_yearly = data_span_days >= 365
    if not use_yearly:
        print(f"  NOTE: Data spans only {data_span_days} days — yearly seasonality disabled "
              "(requires >= 365 days of history).")

    model = Prophet(
        yearly_seasonality=use_yearly,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=PROPHET_INTERVAL_WIDTH,
        changepoint_prior_scale=PROPHET_CHANGEPOINT_PRIOR,
    )
    model.fit(df)

    future = model.make_future_dataframe(periods=FORECAST_DAYS, freq="D")
    forecast = model.predict(future)
    return model, forecast


# ─────────────────────────────────────────────────────────────────────────────
# 3. Visualisations
# ─────────────────────────────────────────────────────────────────────────────

def plot_forecast(df_actual: pd.DataFrame, forecast: pd.DataFrame,
                  category: str) -> str:
    """
    Chart 05 — Actual demand vs. Prophet forecast with 95% CI.
    Highlights the upper-bound (worst-case) planning line.
    """
    fig, ax = plt.subplots(figsize=(14, 6))

    # ── Historical actuals ────────────────────────────────────────────────
    ax.scatter(df_actual["ds"], df_actual["y"],
               s=6, color="#2c7bb6", alpha=0.55, label="Historical Demand (actual)", zorder=3)

    # ── Forecast mean ─────────────────────────────────────────────────────
    future_fc = forecast[forecast["ds"] > df_actual["ds"].max()].copy()
    ax.plot(forecast["ds"], forecast["yhat"],
            color="#1a1a2e", linewidth=1.4, label="Forecast (mean)", zorder=4)

    # ── 95% CI band ───────────────────────────────────────────────────────
    ax.fill_between(forecast["ds"], forecast["yhat_lower"], forecast["yhat_upper"],
                    alpha=0.18, color="#2c7bb6", label="95% Confidence Interval")

    # ── Worst-case upper bound (planning line) ────────────────────────────
    ax.plot(future_fc["ds"], future_fc["yhat_upper"],
            color="#d7191c", linewidth=1.5, linestyle="--",
            label="Worst-Case Upper Bound (procurement plan)", zorder=5)

    # ── Divider between history and forecast ─────────────────────────────
    cutoff = df_actual["ds"].max()
    ax.axvline(cutoff, color="grey", linewidth=1, linestyle=":", alpha=0.8)
    ax.text(cutoff, ax.get_ylim()[1] * 0.95, "  Forecast →",
            color="grey", fontsize=9, va="top")

    ax.set_title(
        f"90-Day Demand Forecast — {category}\n"
        "Worst-case upper bound used as procurement planning input (95% Service Level)",
        fontsize=13, fontweight="bold", pad=14
    )
    ax.set_xlabel("Date", labelpad=8)
    ax.set_ylabel("Daily Order Quantity (units)", labelpad=8)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    fig.autofmt_xdate()

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, "05_demand_forecast.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_seasonality(model, forecast: pd.DataFrame, category: str) -> str:
    """
    Chart 06 — Prophet seasonality components (weekly + yearly).
    Uses Prophet's built-in plot_components but applies a custom title.
    Reuses the already-computed forecast — no redundant second prediction.
    """
    fig = model.plot_components(forecast)
    fig.set_size_inches(12, 8)
    fig.suptitle(
        f"Demand Seasonality Components — {category}\n"
        "Weekly and Yearly patterns extracted by Prophet decomposition",
        fontsize=12, fontweight="bold", y=1.01
    )
    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, "06_seasonality_analysis.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# 4. Terminal summary report
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(forecast: pd.DataFrame, df_actual: pd.DataFrame, category: str):
    cutoff = df_actual["ds"].max()
    future_fc = forecast[forecast["ds"] > cutoff].copy()

    next_30  = future_fc.head(30)
    next_90  = future_fc

    avg_30_mean  = next_30["yhat"].mean()
    avg_30_upper = next_30["yhat_upper"].mean()
    avg_90_mean  = next_90["yhat"].mean()
    avg_90_upper = next_90["yhat_upper"].mean()
    peak_day     = future_fc.loc[future_fc["yhat_upper"].idxmax()]

    divider = "─" * 60

    print()
    print(divider)
    print("  DEMAND FORECAST SUMMARY REPORT")
    print(f"  Category  : {category}")
    print(f"  Horizon   : {FORECAST_DAYS} days from {cutoff.strftime('%Y-%m-%d')}")
    print(divider)
    print()
    print("  NEXT 30 DAYS")
    print(f"    Average Predicted Daily Demand  : {avg_30_mean:>8.1f} units  (mean)")
    print(f"    Worst-Case Upper Bound (95% CI) : {avg_30_upper:>8.1f} units  ← use for procurement")
    print()
    print("  NEXT 90 DAYS")
    print(f"    Average Predicted Daily Demand  : {avg_90_mean:>8.1f} units  (mean)")
    print(f"    Worst-Case Upper Bound (95% CI) : {avg_90_upper:>8.1f} units  ← use for procurement")
    print()
    print("  PEAK RISK DATE (highest upper bound)")
    print(f"    Date                            : {peak_day['ds'].strftime('%Y-%m-%d')}")
    print(f"    Worst-Case Demand               : {peak_day['yhat_upper']:>8.1f} units")
    print()
    print("  SCA NOTE: The Upper Bound is the conservative planning figure.")
    print("  Ordering to the mean risks a stockout in 1 of every 20 periods.")
    print("  Ordering to the upper bound protects against demand spikes at")
    print("  the 95% service level, minimising lost-sales cost.")
    print()
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

    # ── Identify target category ─────────────────────────────────────────
    print("Identifying highest-volume product category...")
    try:
        category = fetch_top_categories(engine, 1)[0]
        print(f"  Target category: {category}\n")
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Pull historical demand ────────────────────────────────────────────
    print(f"Extracting daily demand history for '{category}'...")
    try:
        df = fetch_daily_demand(engine, category)
        print(f"  {len(df):,} daily records loaded  "
              f"({df['ds'].min().strftime('%Y-%m-%d')} → {df['ds'].max().strftime('%Y-%m-%d')})\n")
    except Exception as exc:
        print(f"  ERROR fetching demand data — {exc}", file=sys.stderr)
        sys.exit(1)

    if len(df) < 60:
        print("  WARNING: Fewer than 60 data points available. "
              "Forecast accuracy may be limited.", file=sys.stderr)

    # ── Fit model & forecast ──────────────────────────────────────────────
    print(f"Fitting Prophet model and forecasting {FORECAST_DAYS} days ahead...")
    try:
        model, forecast = build_and_run_model(df)
        print("  Model training complete.\n")
    except Exception as exc:
        print(f"  ERROR during model fitting — {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Chart 05: Forecast plot ───────────────────────────────────────────
    print("[1/2] Generating Demand Forecast chart...")
    try:
        path = plot_forecast(df, forecast, category)
        print(f"  Saved → {path}\n")
    except Exception as exc:
        print(f"  ERROR generating forecast chart — {exc}", file=sys.stderr)

    # ── Chart 06: Seasonality components ─────────────────────────────────
    print("[2/2] Generating Seasonality Analysis chart...")
    try:
        path = plot_seasonality(model, forecast, category)
        print(f"  Saved → {path}\n")
    except Exception as exc:
        print(f"  ERROR generating seasonality chart — {exc}", file=sys.stderr)

    # ── Terminal summary ──────────────────────────────────────────────────
    print_summary(forecast, df, category)


if __name__ == "__main__":
    main()
