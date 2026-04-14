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
    """Return a SQLAlchemy engine.

    When running on Streamlit Cloud, credentials are read from st.secrets
    (set via the Streamlit Cloud UI). Locally, .env values are used.
    """
    user, password, host, name = DB_USER, DB_PASSWORD, DB_HOST, DB_NAME
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            user     = st.secrets.get("DB_USER",     user)
            password = st.secrets.get("DB_PASSWORD", password)
            host     = st.secrets.get("DB_HOST",     host)
            name     = st.secrets.get("DB_NAME",     name)
    except Exception:
        pass
    url = f"mysql+pymysql://{user}:{password}@{host}/{name}"
    return create_engine(url, pool_pre_ping=True)
