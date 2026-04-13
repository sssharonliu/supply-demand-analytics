# Supply-Demand Intelligence System
### Turning 180,000+ Supply Chain Records into Actionable Operational Risk Intelligence

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?style=flat&logo=mysql&logoColor=white)](https://www.mysql.com/)
[![Pandas](https://img.shields.io/badge/Pandas-2.x-150458?style=flat&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![Seaborn](https://img.shields.io/badge/Seaborn-Visualization-4C72B0?style=flat)](https://seaborn.pydata.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-D71F00?style=flat)](https://www.sqlalchemy.org/)

---

## Overview

This project is an end-to-end supply chain analytics system built on the **DataCo Smart Supply Chain dataset** (180,519 real-world order records). It ingests raw transactional data into a relational database, runs SQL-based KPI analysis, and surfaces operational risks through automated BI dashboards — answering three critical business questions:

- **Where is demand unpredictable?** (inventory over-stocking risk)
- **Which shipping modes are failing?** (service-level agreement breaches)
- **Which categories are high-revenue but low-margin?** (profitability leaks)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data Ingestion | Python · Pandas · SQLAlchemy |
| Database | MySQL 8.0 |
| Analytics Engine | SQL (CTEs, Window Functions, Aggregations) |
| Visualization | Matplotlib · Seaborn |
| Dataset | DataCo Smart Supply Chain (Kaggle) — 180,519 rows |

---

## System Architecture

```
Raw CSV Data (180K+ rows)
        │
        ▼
┌─────────────────────┐
│   ingest_data.py    │  ← Cleans column names, handles encoding,
│   (ETL Pipeline)    │    loads into MySQL via SQLAlchemy bulk insert
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  MySQL Database     │  ← supply_chain_db.orders
│  (supply_chain_db)  │    Single denormalized fact table
└─────────────────────┘
        │
        ▼
┌──────────────────────────┐
│   visualize_insights.py  │  ← Executes KPI queries, renders charts,
│   (BI Dashboard Engine)  │    saves high-res PNGs to dashboards/
└──────────────────────────┘
        │
        ▼
┌─────────────────────┐
│  dashboards/*.png   │  ← Demand Volatility · Supply Reliability
│  (Exported Charts)  │    · Inventory Health
└─────────────────────┘
```

---

## Dashboard Showcase

### Chart 1 — Demand Volatility

![Demand Volatility](dashboards/01_demand_volatility.png)

**Business Insight:**
The Coefficient of Variation (CV = σ/μ) measures how erratic monthly sales are relative to their average — a higher score means less predictable demand and higher inventory risk. **Cameras** top the chart with a CV near **0.94**, meaning their monthly sales swing by nearly the full average order volume. Categories like *Cardio Equipment* and *Lacrosse* follow closely. For supply planners, these high-CV categories are prime candidates for safety stock reviews, as current reorder points are likely calibrated against a false sense of stability.

---

### Chart 2 — Supply Reliability

![Supply Reliability](dashboards/02_supply_reliability.png)

**Business Insight:**
Of all completed orders shipped via **Second Class**, **79.80% arrived late** — a near-total failure of the expected delivery SLA. This is not a marginal overrun; it signals that Second Class shipping is systematically misaligned between scheduled and actual transit times. First Class and Standard Class perform significantly better, suggesting the issue is carrier-specific or that scheduled windows for Second Class were never realistically calibrated. This finding alone has direct cost implications: late deliveries erode customer trust, trigger chargebacks, and inflate customer service overhead.

---

### Chart 3 — Inventory Health

![Inventory Health](dashboards/03_inventory_health.png)

**Business Insight:**
This scatter plot maps every product category on two dimensions simultaneously: total revenue generated (X-axis) and average profit extracted per order (Y-axis). Categories in the **upper-right quadrant** are the business's core value drivers — high sales *and* healthy margins. Categories near or **below the zero-profit line** (red dashed) are revenue traps: they move volume but destroy margin, often due to discounting, high return rates, or poor supplier terms. This view enables category managers to prioritize margin-recovery initiatives where they will have the highest financial impact.

---

## How to Run

### Prerequisites

- Python 3.9+
- MySQL 8.0 running locally
- An empty database named `supply_chain_db`

```sql
-- Run once in MySQL Workbench or mysql CLI
CREATE DATABASE supply_chain_db;
```

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Add the dataset

Download the **DataCo Smart Supply Chain** dataset from Kaggle and place the CSV at:

```
data/raw/DataCoSupplyChainDataset.csv
```

### 3. Run the ETL pipeline

```bash
python ingest_data.py
```

This cleans and loads all 180,519 rows into `supply_chain_db.orders`. Expect 1–2 minutes for the bulk insert.

### 4. Generate the dashboards

```bash
python visualize_insights.py
```

Charts are saved to `dashboards/` on completion.

---

## Project Structure

```
Supply-Demand-Analytics/
├── data/
│   └── raw/                        # Source CSV (not tracked in git)
├── dashboards/
│   ├── 01_demand_volatility.png
│   ├── 02_supply_reliability.png
│   └── 03_inventory_health.png
├── sql/
│   ├── 01_demand_volatility.sql    # Standalone KPI queries
│   └── 02_supply_reliability.sql
├── notebooks/                      # Exploratory analysis
├── ingest_data.py                  # ETL pipeline
├── visualize_insights.py           # BI dashboard engine
└── requirements.txt
```

---

## Key Findings Summary

| KPI | Finding | Business Impact |
|---|---|---|
| Demand Volatility | Cameras CV ≈ 0.94 — highest in portfolio | Safety stock model needs recalibration for top-10 volatile categories |
| Supply Reliability | Second Class shipping: 79.80% late delivery rate | Carrier SLA renegotiation or mode substitution required |
| Inventory Health | Several high-revenue categories show near-zero or negative margins | Margin recovery opportunities through pricing or supplier terms |

---

## Roadmap

### Phase 1 — Operational Risk Baseline ✅ *(current)*
- Automated ETL pipeline (CSV → MySQL)
- SQL-based KPI analytics engine
- Automated BI dashboards (Demand Volatility, Supply Reliability, Inventory Health)

### Phase 2 — AI-Driven Forecasting *(planned)*
- **Demand Forecasting** using Facebook Prophet / ARIMA on time-series order data
- **Safety Stock Optimization** — compute dynamic reorder points per category using forecast uncertainty bands
- **Anomaly Detection** — flag orders that are statistical outliers in lead time or discount rate

### Phase 3 — Interactive Reporting *(planned)*
- Tableau or Streamlit dashboard for live exploration
- Scheduled pipeline runs with automated report delivery

---

## Dataset

**DataCo Smart Supply Chain for Big Data Analysis**
Fabian Constante, Fernando Silva, António Pereira — Mendeley Data, 2019.
[https://data.mendeley.com/datasets/8gx2fvg2k6/5](https://data.mendeley.com/datasets/8gx2fvg2k6/5)
