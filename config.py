"""
config.py
─────────
Single source of truth for database credentials, connection factory,
and shared constants used across all analytics scripts.

All scripts should import from here instead of defining their own
get_engine() or hardcoding credentials.

Usage:
    from config import get_engine, OUTPUT_DIR, DB_NAME
"""

import os
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Resolve paths relative to this file so scripts work from any cwd
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, ".env"))

DB_USER     = os.getenv("DB_USER",     "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_NAME     = os.getenv("DB_NAME",     "supply_chain_db")

OUTPUT_DIR  = os.path.join(_BASE_DIR, "dashboards")


def get_engine():
    """Return a SQLAlchemy engine connected to the configured MySQL database."""
    url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
    return create_engine(url, pool_pre_ping=True)
