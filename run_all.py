"""
run_all.py
──────────
Full pipeline orchestrator — runs all four scripts in the correct order.

Usage:
    python3 run_all.py              # run all stages
    python3 run_all.py --skip-ingest  # skip data ingestion (DB already loaded)

Stages:
  1. ingest_data          — ETL: CSV → MySQL
  2. visualize_insights   — Charts 01–03 (Demand Volatility, Supply Reliability, Inventory Health)
  3. inventory_optimization — Chart 04 + CSV policy table (Safety Stock, ROP)
  4. demand_forecasting   — Charts 05–06 (90-day forecast, seasonality)
"""

import os
import sys
import time
import argparse

# Ensure working directory is the script's folder
os.chdir(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────────────────────

def preflight():
    """Fail fast on missing .env or unreachable database before running anything."""
    errors = []

    # .env exists
    if not os.path.exists(".env"):
        errors.append(".env file not found. Copy .env.example to .env and fill in credentials.")

    # config importable (also validates dotenv + sqlalchemy)
    try:
        from config import get_engine
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        errors.append(f"Database connection failed: {exc}")

    if errors:
        print("Pre-flight checks FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    print("Pre-flight checks passed.\n")


# ─────────────────────────────────────────────────────────────────────────────
# Stage runner
# ─────────────────────────────────────────────────────────────────────────────

def run_stage(name: str, fn) -> tuple[bool, float]:
    """Run a stage function; return (success, elapsed_seconds)."""
    divider = "─" * 60
    print(divider)
    print(f"  STAGE: {name}")
    print(divider)
    t0 = time.time()
    try:
        fn()
        elapsed = time.time() - t0
        print(f"\n  [{name}] completed in {elapsed:.1f}s\n")
        return True, elapsed
    except SystemExit as exc:
        elapsed = time.time() - t0
        # sys.exit(1) from a sub-script counts as failure
        if exc.code != 0:
            print(f"\n  [{name}] FAILED (exit code {exc.code}) after {elapsed:.1f}s\n",
                  file=sys.stderr)
            return False, elapsed
        return True, elapsed
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"\n  [{name}] FAILED: {exc} (after {elapsed:.1f}s)\n", file=sys.stderr)
        return False, elapsed


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Supply Chain Analytics — Full Pipeline")
    parser.add_argument(
        "--skip-ingest", action="store_true",
        help="Skip data ingestion (use when DB is already populated)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  SUPPLY CHAIN ANALYTICS — FULL PIPELINE")
    print("=" * 60 + "\n")

    preflight()

    # Import stage modules after preflight so import errors surface cleanly
    import ingest_data
    import visualize_insights
    import inventory_optimization
    import demand_forecasting

    stages = []

    if not args.skip_ingest:
        stages.append(("1/4  Data Ingestion",         ingest_data.run_ingestion))
    else:
        print("Skipping data ingestion (--skip-ingest).\n")

    stages += [
        ("2/4  BI Dashboards (Charts 01-03)",  visualize_insights.main),
        ("3/4  Inventory Policy (Chart 04)",   inventory_optimization.main),
        ("4/4  Demand Forecasting (Charts 05-06)", demand_forecasting.main),
    ]

    results = {}
    pipeline_start = time.time()

    for name, fn in stages:
        success, elapsed = run_stage(name, fn)
        results[name] = (success, elapsed)

        # Ingestion failure is a hard stop — no point running analytics on stale data
        if not success and "Ingestion" in name:
            print("Ingestion failed — aborting pipeline.", file=sys.stderr)
            sys.exit(1)

    # ── Final summary ─────────────────────────────────────────────────────
    total = time.time() - pipeline_start
    divider = "=" * 60
    print(divider)
    print("  PIPELINE SUMMARY")
    print(divider)
    for name, (success, elapsed) in results.items():
        status = "PASS" if success else "FAIL"
        print(f"  [{status}]  {name:<42}  {elapsed:>5.1f}s")
    print(divider)
    print(f"  Total elapsed: {total:.1f}s")
    print(divider)

    failed = [n for n, (ok, _) in results.items() if not ok]
    if failed:
        print(f"\n  {len(failed)} stage(s) failed.", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n  All stages completed successfully.")


if __name__ == "__main__":
    main()
