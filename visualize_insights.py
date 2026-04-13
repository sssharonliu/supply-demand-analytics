import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from sqlalchemy import create_engine, text

# Ensure working directory is the script's folder
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# --- Configuration ---
DB_USER = "root"
DB_PASSWORD = "password123"
DB_HOST = "localhost"
DB_NAME = "supply_chain_db"
OUTPUT_DIR = "dashboards"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Apply a clean seaborn theme globally
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)


def get_engine():
    url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
    return create_engine(url)


# ---------------------------------------------------------------------------
# Chart 1 — Demand Volatility (Top 10 categories by monthly CV)
# ---------------------------------------------------------------------------
def chart_demand_volatility(engine):
    print("[1/3] Generating Demand Volatility chart...")

    sql = text("""
        WITH monthly_sales AS (
            SELECT
                category_name,
                DATE_FORMAT(
                    STR_TO_DATE(order_date_dateorders, '%m/%d/%Y %H:%i'),
                    '%Y-%m'
                ) AS month,
                SUM(sales) AS monthly_sales
            FROM orders
            WHERE order_status NOT IN ('CANCELED', 'SUSPECTED_FRAUD')
              AND order_date_dateorders IS NOT NULL
            GROUP BY category_name, month
        ),
        cv_calc AS (
            SELECT
                category_name,
                AVG(monthly_sales)                          AS mean_sales,
                STDDEV_SAMP(monthly_sales)                  AS stddev_sales,
                STDDEV_SAMP(monthly_sales) / AVG(monthly_sales) AS cv
            FROM monthly_sales
            GROUP BY category_name
            HAVING mean_sales > 0 AND stddev_sales IS NOT NULL
        )
        SELECT category_name, ROUND(cv, 4) AS cv
        FROM cv_calc
        ORDER BY cv DESC
        LIMIT 10
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)

    if df.empty:
        print("  WARNING: No data returned for Demand Volatility. Skipping.")
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(df["category_name"], df["cv"], color=sns.color_palette("Reds_r", len(df)))
    ax.invert_yaxis()
    ax.set_xlabel("Coefficient of Variation (CV = σ / μ)", labelpad=10)
    ax.set_title("Demand Volatility — Top 10 Categories by Monthly CV", fontsize=14, fontweight="bold", pad=15)

    for bar, val in zip(bars, df["cv"]):
        ax.text(
            bar.get_width() + 0.002, bar.get_y() + bar.get_height() / 2,
            f"{val:.3f}", va="center", ha="left", fontsize=9
        )

    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, "01_demand_volatility.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {out_path}")


# ---------------------------------------------------------------------------
# Chart 2 — Supply Reliability (Late delivery rate by shipping mode)
# ---------------------------------------------------------------------------
def chart_supply_reliability(engine):
    print("[2/3] Generating Supply Reliability chart...")

    sql = text("""
        SELECT
            shipping_mode,
            COUNT(*)                                                        AS total_orders,
            SUM(CASE WHEN days_for_shipping_real > days_for_shipment_scheduled
                     THEN 1 ELSE 0 END)                                     AS late_orders,
            ROUND(
                100.0 * SUM(CASE WHEN days_for_shipping_real > days_for_shipment_scheduled
                                 THEN 1 ELSE 0 END) / COUNT(*),
                2
            )                                                               AS late_rate_pct
        FROM orders
        WHERE order_status = 'COMPLETE'
          AND shipping_mode IS NOT NULL
        GROUP BY shipping_mode
        ORDER BY late_rate_pct DESC
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)

    if df.empty:
        print("  WARNING: No data returned for Supply Reliability. Skipping.")
        return

    palette = sns.color_palette("Blues_d", len(df))
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(df["shipping_mode"], df["late_rate_pct"], color=palette, edgecolor="white", linewidth=0.8)

    for bar, val in zip(bars, df["late_rate_pct"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
            f"{val:.1f}%", ha="center", va="bottom", fontsize=10, fontweight="bold"
        )

    ax.set_ylabel("Late Delivery Rate (%)", labelpad=10)
    ax.set_xlabel("Shipping Mode", labelpad=10)
    ax.set_title("Supply Reliability — Late Delivery Rate by Shipping Mode\n(COMPLETE orders only)",
                 fontsize=13, fontweight="bold", pad=15)
    ax.set_ylim(0, df["late_rate_pct"].max() * 1.2)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, "02_supply_reliability.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {out_path}")


# ---------------------------------------------------------------------------
# Chart 3 — Inventory Health (Sales vs. Profit per category)
# ---------------------------------------------------------------------------
def chart_inventory_health(engine):
    print("[3/3] Generating Inventory Health chart...")

    sql = text("""
        SELECT
            category_name,
            SUM(sales)                          AS total_sales,
            AVG(order_profit_per_order)         AS avg_profit
        FROM orders
        WHERE category_name IS NOT NULL
        GROUP BY category_name
        ORDER BY total_sales DESC
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)

    if df.empty:
        print("  WARNING: No data returned for Inventory Health. Skipping.")
        return

    fig, ax = plt.subplots(figsize=(11, 7))
    scatter = ax.scatter(
        df["total_sales"], df["avg_profit"],
        s=120, alpha=0.85,
        c=df["avg_profit"],
        cmap="RdYlGn", edgecolors="grey", linewidths=0.5
    )

    # Label each point with its category name
    for _, row in df.iterrows():
        ax.annotate(
            row["category_name"],
            xy=(row["total_sales"], row["avg_profit"]),
            xytext=(5, 4), textcoords="offset points",
            fontsize=7.5, color="dimgrey"
        )

    cbar = fig.colorbar(scatter, ax=ax, pad=0.02)
    cbar.set_label("Avg Profit per Order ($)", rotation=270, labelpad=15)

    ax.axhline(0, color="red", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"${y:,.1f}"))
    ax.set_xlabel("Total Sales ($)", labelpad=10)
    ax.set_ylabel("Avg Profit per Order ($)", labelpad=10)
    ax.set_title("Inventory Health — Sales vs. Average Profit by Category",
                 fontsize=13, fontweight="bold", pad=15)

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, "03_inventory_health.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Connecting to database...")
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("  Connection successful.\n")
    except Exception as exc:
        print(f"  ERROR: Could not connect to database — {exc}", file=sys.stderr)
        sys.exit(1)

    errors = []

    for chart_fn in (chart_demand_volatility, chart_supply_reliability, chart_inventory_health):
        try:
            chart_fn(engine)
        except Exception as exc:
            msg = f"  ERROR in {chart_fn.__name__}: {exc}"
            print(msg, file=sys.stderr)
            errors.append(msg)

    print()
    if errors:
        print(f"Finished with {len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("All 3 charts generated successfully.")


if __name__ == "__main__":
    main()
