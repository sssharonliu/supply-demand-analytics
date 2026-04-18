import os
import sys
import logging
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# ── Working directory ─────────────────────────────────────────────────────────
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/ingest.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Credentials ───────────────────────────────────────────────────────────────
load_dotenv()
DB_USER     = os.getenv("DB_USER",     "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_NAME     = os.getenv("DB_NAME",     "supply_chain_db")

# ── Constants ─────────────────────────────────────────────────────────────────
CSV_PATH   = "data/raw/DataCoSupplyChainDataset.csv"
TABLE_NAME = "orders"

# Columns that must exist in the CSV for downstream analytics to work
REQUIRED_COLUMNS = [
    "order_item_quantity",
    "order_date_dateorders",
    "category_name",
    "days_for_shipping_real",
    "days_for_shipment_scheduled",
    "order_status",
    "sales",
    "order_profit_per_order",
]

# Columns to coerce to numeric (non-convertible values become NaN)
NUMERIC_COLUMNS = [
    "order_item_quantity",
    "days_for_shipping_real",
    "days_for_shipment_scheduled",
    "sales",
    "order_profit_per_order",
    "order_item_discount",
    "order_item_discount_rate",
    "order_item_product_price",
    "order_item_profit_ratio",
    "order_item_total",
    "order_profit_per_order",
]

# String columns worth stripping of whitespace
STRING_COLUMNS = [
    "category_name",
    "order_status",
    "shipping_mode",
    "customer_country",
    "order_country",
    "market",
    "department_name",
    "product_name",
]

# Unique identifier for duplicate detection
ORDER_ID_COLUMN = "order_id"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Load
# ─────────────────────────────────────────────────────────────────────────────

def load_csv() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(
            f"Dataset not found at '{CSV_PATH}'. "
            "Download it from Kaggle and place it there."
        )
    log.info("Reading CSV: %s", CSV_PATH)
    df = pd.read_csv(CSV_PATH, encoding="latin-1", low_memory=False)
    log.info("  %s rows, %s columns loaded.", f"{len(df):,}", len(df.columns))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2. Clean
# ─────────────────────────────────────────────────────────────────────────────

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names: lowercase, no spaces or special chars."""
    import re
    df.columns = [
        re.sub(r"_+", "_",                    # collapse consecutive underscores
            re.sub(r"[^a-z0-9_]", "_",        # replace anything non-alphanum with _
                c.lower().strip()
            )
        ).strip("_")
        for c in df.columns
    ]
    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Light, non-destructive cleaning:
    - Strip leading/trailing whitespace from string columns
    - Coerce numeric columns to float (bad values → NaN, not dropped)
    """
    # Strip whitespace from string columns that exist in this dataset
    for col in STRING_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace("nan", pd.NA)

    # Coerce numeric columns
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            original_nulls = df[col].isna().sum()
            df[col] = pd.to_numeric(df[col], errors="coerce")
            new_nulls = df[col].isna().sum() - original_nulls
            if new_nulls > 0:
                log.warning("  '%s': %s non-numeric values coerced to NaN.", col, f"{new_nulls:,}")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validate source
# ─────────────────────────────────────────────────────────────────────────────

def validate_source(df: pd.DataFrame):
    """Fail fast on missing required columns; warn on high null rates and duplicates."""
    # Required columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {missing}\n"
            "Check that you have the correct DataCo dataset version."
        )

    # Null rate warnings
    for col in REQUIRED_COLUMNS:
        null_pct = df[col].isna().mean() * 100
        if null_pct > 20:
            log.warning("  '%s' is %.1f%% null — downstream results may be unreliable.", col, null_pct)
        elif null_pct > 0:
            log.info("  '%s': %.1f%% null (acceptable).", col, null_pct)

    # Duplicate order IDs
    if ORDER_ID_COLUMN in df.columns:
        dupes = df[ORDER_ID_COLUMN].duplicated().sum()
        if dupes:
            log.warning(
                "  %s duplicate %s values found. Each order may have multiple "
                "line items — confirm this is expected before aggregating.",
                f"{dupes:,}", ORDER_ID_COLUMN
            )
        else:
            log.info("  No duplicate %s values.", ORDER_ID_COLUMN)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Ingest
# ─────────────────────────────────────────────────────────────────────────────

def get_engine():
    url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
    return create_engine(url, pool_pre_ping=True)


def ingest(engine, df: pd.DataFrame):
    """
    Safe re-run pattern: truncate existing table, then bulk-insert.
    - Never issues DROP TABLE, preserving any indexes added post-ingestion.
    - Uses method='multi' for significantly faster multi-row INSERT statements.
    """
    with engine.begin() as conn:
        exists = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = :db AND table_name = :tbl"
        ), {"db": DB_NAME, "tbl": TABLE_NAME}).scalar()

        if exists:
            log.info("Table `%s` exists — truncating before reload.", TABLE_NAME)
            conn.execute(text(f"TRUNCATE TABLE {TABLE_NAME}"))

    log.info("Inserting %s rows (bulk multi-row insert)...", f"{len(df):,}")
    df.to_sql(
        TABLE_NAME,
        con=engine,
        if_exists="append",
        index=False,
        chunksize=1000,
        method="multi",   # batches values into a single INSERT per chunk — ~5-10x faster than default
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Validate result
# ─────────────────────────────────────────────────────────────────────────────

def ensure_indexes(engine):
    """
    Create analytics indexes after ingestion if they don't already exist.
    TRUNCATE (used on re-run) preserves indexes, so this is idempotent.
    """
    indexes = [
        # Speeds up GROUP BY category + date in demand queries (all analytics scripts)
        ("idx_cat_date",  f"CREATE INDEX idx_cat_date ON {TABLE_NAME}(category_name, order_date_dateorders)"),
        # Speeds up shipping-mode reliability analysis in visualize_insights.py
        ("idx_shipping",  f"CREATE INDEX idx_shipping ON {TABLE_NAME}(shipping_mode, order_status)"),
    ]
    with engine.begin() as conn:
        for idx_name, ddl in indexes:
            exists = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = :db AND table_name = :tbl AND index_name = :idx"
            ), {"db": DB_NAME, "tbl": TABLE_NAME, "idx": idx_name}).scalar()
            if not exists:
                conn.execute(text(ddl))
                log.info("  Created index %s.", idx_name)
            else:
                log.info("  Index %s already exists — skipped.", idx_name)


def validate_ingestion(engine, expected_rows: int):
    """Confirm DB row count matches CSV and spot-check critical column nulls."""
    with engine.connect() as conn:
        actual = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).scalar()

    if actual != expected_rows:
        raise RuntimeError(
            f"Row count mismatch: CSV had {expected_rows:,} rows "
            f"but database has {actual:,}. Ingestion may be incomplete."
        )
    log.info("  Row count validated: %s rows in database.", f"{actual:,}")

    with engine.connect() as conn:
        null_qty = conn.execute(text(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE order_item_quantity IS NULL"
        )).scalar()
    if null_qty:
        log.warning("  %s rows have NULL order_item_quantity.", f"{null_qty:,}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Summary report
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame):
    divider = "─" * 55
    log.info(divider)
    log.info("INGESTION SUMMARY")
    log.info(divider)
    log.info("  Total rows        : %s", f"{len(df):,}")
    log.info("  Total columns     : %s", len(df.columns))

    if "category_name" in df.columns:
        log.info("  Unique categories : %s", df["category_name"].nunique())

    if "order_status" in df.columns:
        log.info("  Order statuses    : %s", sorted(df["order_status"].dropna().unique().tolist()))

    if "order_date_dateorders" in df.columns:
        # Parse a sample to get date range without full parse overhead
        sample = pd.to_datetime(
            df["order_date_dateorders"].dropna().iloc[::100],
            format="%m/%d/%Y %H:%M", errors="coerce"
        ).dropna()
        if not sample.empty:
            log.info("  Date range (est.) : %s → %s",
                     sample.min().strftime("%Y-%m-%d"),
                     sample.max().strftime("%Y-%m-%d"))

    log.info("  Null rates (required columns):")
    for col in REQUIRED_COLUMNS:
        if col in df.columns:
            pct = df[col].isna().mean() * 100
            log.info("    %-36s %.1f%%", col, pct)

    log.info(divider)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run_ingestion():
    # 1. Load
    try:
        df = load_csv()
    except Exception as exc:
        log.error("Failed to load CSV: %s", exc)
        sys.exit(1)

    # 2. Clean column names
    df = clean_columns(df)

    # 3. Clean data
    log.info("Cleaning data...")
    df = clean_data(df)

    # 4. Validate source
    log.info("Validating source data...")
    try:
        validate_source(df)
        log.info("  Source validation passed.")
    except ValueError as exc:
        log.error("%s", exc)
        sys.exit(1)

    # 5. Connect
    log.info("Connecting to MySQL (%s@%s/%s)...", DB_USER, DB_HOST, DB_NAME)
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("  Connection successful.")
    except Exception as exc:
        log.error("Could not connect to database: %s", exc)
        sys.exit(1)

    # 6. Ingest
    try:
        ingest(engine, df)
    except Exception as exc:
        log.error("Ingestion failed: %s", exc)
        sys.exit(1)

    # 7. Indexes
    log.info("Ensuring analytics indexes...")
    try:
        ensure_indexes(engine)
    except Exception as exc:
        log.warning("Index creation failed (non-fatal): %s", exc)

    # 8. Validate result
    log.info("Validating ingestion...")
    try:
        validate_ingestion(engine, expected_rows=len(df))
    except RuntimeError as exc:
        log.error("%s", exc)
        sys.exit(1)

    # 9. Summary
    print_summary(df)
    log.info("Ingestion complete. Log saved to logs/ingest.log")


if __name__ == "__main__":
    run_ingestion()
