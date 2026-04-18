"""
data.py
───────
Shared database query helpers used by demand_forecasting.py,
prepare_deployment.py, and dashboard.py.

All functions accept a SQLAlchemy engine so callers control connection lifecycle.
"""

import pandas as pd
from sqlalchemy import text


def fetch_daily_demand(engine, category: str) -> pd.DataFrame:
    """
    Pull daily aggregated order quantity for one category.
    Returns DataFrame with columns [ds, y], filtered to positive quantities
    and excluding CANCELED / SUSPECTED_FRAUD orders.
    """
    sql = text("""
        SELECT
            DATE(STR_TO_DATE(order_date_dateorders, '%m/%d/%Y %H:%i')) AS ds,
            SUM(order_item_quantity)                                    AS y
        FROM orders
        WHERE category_name   = :cat
          AND order_status NOT IN ('CANCELED', 'SUSPECTED_FRAUD')
          AND order_date_dateorders IS NOT NULL
        GROUP BY ds
        ORDER BY ds
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"cat": category})
    df["ds"] = pd.to_datetime(df["ds"])
    return df.dropna(subset=["ds", "y"]).query("y > 0").reset_index(drop=True)


def fetch_top_categories(engine, n: int) -> list[str]:
    """Return the top-n categories by total order quantity, descending."""
    sql = text("""
        SELECT category_name, SUM(order_item_quantity) AS total_qty
        FROM orders
        WHERE category_name      IS NOT NULL
          AND order_item_quantity IS NOT NULL
        GROUP BY category_name
        ORDER BY total_qty DESC
        LIMIT :n
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"n": n})
    return df["category_name"].tolist()
