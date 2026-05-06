"""
Polymarket + Kalshi Alpha Dashboard
============================================================
Interactive Streamlit dashboard for visualising:
  - Daily price snapshots (SPY, SPX, QQQ)
  - Volume trends
  - Cross-market arbitrage opportunities
  - Whale concentration

Usage (local):
    streamlit run dashboard.py

Environment:
    DATABASE_URL — PostgreSQL connection string (optional)
============================================================
"""

import os
import json
import random
from datetime import date, timedelta
from typing import Optional, List, Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ------------------------------------------------------------------
# Database helpers (best-effort)
# ------------------------------------------------------------------
try:
    import psycopg2
    HAS_DB = True
except ImportError:
    HAS_DB = False


def get_db_conn():
    if not HAS_DB:
        return None
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    try:
        return psycopg2.connect(url)
    except Exception:
        return None


# ------------------------------------------------------------------
# Demo data generators (used when DATABASE_URL is missing)
# ------------------------------------------------------------------

def _demo_dates(days: int = 14) -> List[date]:
    today = date.today()
    return [today - timedelta(days=i) for i in range(days, 0, -1)]


def _demo_markets() -> pd.DataFrame:
    """Return a DataFrame of dummy markets."""
    markets = [
        {"id": 1, "platform": "polymarket", "question": "SPY up today?", "category": "Equity"},
        {"id": 2, "platform": "polymarket", "question": "SPX above 5200?", "category": "Equity"},
        {"id": 3, "platform": "polymarket", "question": "QQQ green?", "category": "Equity"},
        {"id": 4, "platform": "kalshi", "question": "SPY up today?", "category": "Equity"},
        {"id": 5, "platform": "kalshi", "question": "SPX above 5200?", "category": "Equity"},
        {"id": 6, "platform": "polymarket", "question": "Trump wins 2024?", "category": "Politics"},
        {"id": 7, "platform": "kalshi", "question": "Trump wins 2024?", "category": "Politics"},
    ]
    return pd.DataFrame(markets)


def _demo_snapshots() -> pd.DataFrame:
    """Return dummy daily snapshots for demo markets."""
    dates = _demo_dates(14)
    rows = []
    for d in dates:
        rows.append({"market_id": 1, "snapshot_date": d, "yes_price": 0.55 + random.uniform(-0.08, 0.08), "volume": 120000 + random.randint(-20000, 20000), "platform": "polymarket", "question": "SPY up today?"})
        rows.append({"market_id": 2, "snapshot_date": d, "yes_price": 0.48 + random.uniform(-0.06, 0.06), "volume": 95000 + random.randint(-15000, 15000), "platform": "polymarket", "question": "SPX above 5200?"})
        rows.append({"market_id": 3, "snapshot_date": d, "yes_price": 0.52 + random.uniform(-0.07, 0.07), "volume": 80000 + random.randint(-10000, 10000), "platform": "polymarket", "question": "QQQ green?"})
        rows.append({"market_id": 4, "snapshot_date": d, "yes_price": 0.57 + random.uniform(-0.08, 0.08), "volume": 45000 + random.randint(-5000, 5000), "platform": "kalshi", "question": "SPY up today?"})
        rows.append({"market_id": 5, "snapshot_date": d, "yes_price": 0.50 + random.uniform(-0.06, 0.06), "volume": 30000 + random.randint(-5000, 5000), "platform": "kalshi", "question": "SPX above 5200?"})
        rows.append({"market_id": 6, "snapshot_date": d, "yes_price": 0.42 + random.uniform(-0.05, 0.05), "volume": 500000 + random.randint(-50000, 50000), "platform": "polymarket", "question": "Trump wins 2024?"})
        rows.append({"market_id": 7, "snapshot_date": d, "yes_price": 0.44 + random.uniform(-0.05, 0.05), "volume": 200000 + random.randint(-20000, 20000), "platform": "kalshi", "question": "Trump wins 2024?"})
    df = pd.DataFrame(rows)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


def _demo_arb() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_name": "SPY up today?", "poly_price": 0.55, "kalshi_price": 0.61, "spread": 0.06},
        {"event_name": "Trump wins 2024?", "poly_price": 0.42, "kalshi_price": 0.49, "spread": 0.07},
        {"event_name": "Fed cuts in June?", "poly_price": 0.30, "kalshi_price": 0.36, "spread": 0.06},
    ])


def _demo_whales() -> pd.DataFrame:
    return pd.DataFrame([
        {"question": "Trump wins 2024?", "top5_pct": 82.5, "total_vol": 580000},
        {"question": "SPY up today?", "top5_pct": 45.0, "total_vol": 145000},
        {"question": "QQQ green?", "top5_pct": 38.0, "total_vol": 89000},
        {"question": "Fed cuts in June?", "top5_pct": 65.0, "total_vol": 210000},
    ])


# ------------------------------------------------------------------
# Real data loaders
# ------------------------------------------------------------------

def load_snapshots(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.market_id, s.snapshot_date, s.outcome_prices, s.volume,
               m.platform, m.question
        FROM price_snapshots s
        JOIN markets m ON m.id = s.market_id
        ORDER BY s.snapshot_date
        """
    )
    rows = cur.fetchall()
    cur.close()

    data = []
    for market_id, snap_date, prices_json, volume, platform, question in rows:
        try:
            prices = prices_json if isinstance(prices_json, list) else json.loads(prices_json)
            yes_price = float(prices[0]) if prices else 0
        except Exception:
            yes_price = 0
        data.append({
            "market_id": market_id,
            "snapshot_date": pd.to_datetime(snap_date),
            "yes_price": yes_price,
            "volume": float(volume or 0),
            "platform": platform,
            "question": question,
        })
    return pd.DataFrame(data)


def load_arbitrage(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT event_name, poly_price_yes, kalshi_price_yes, spread
        FROM arbitrage_opps
        WHERE snapshot_date = CURRENT_DATE
        ORDER BY spread DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    return pd.DataFrame(rows, columns=["event_name", "poly_price", "kalshi_price", "spread"])


# ------------------------------------------------------------------
# Streamlit UI
# ------------------------------------------------------------------

st.set_page_config(page_title="Alpha Dashboard", layout="wide")

st.title("Polymarket + Kalshi Alpha Dashboard")
st.caption("Daily prediction-market data for alpha validation.")

# ------------------------------------------------------------------
# Decide data source
# ------------------------------------------------------------------
conn = get_db_conn()
if conn:
    st.success("Connected to PostgreSQL.")
    df_snap = load_snapshots(conn)
    df_arb = load_arbitrage(conn)
    USE_DEMO = df_snap.empty
else:
    st.warning("DATABASE_URL not set — showing demo data.")
    df_snap = _demo_snapshots()
    df_arb = _demo_arb()
    USE_DEMO = True

if USE_DEMO and conn:
    st.info("Database is empty — falling back to demo data until fetcher populates it.")
    df_snap = _demo_snapshots()
    df_arb = _demo_arb()

# ------------------------------------------------------------------
# KPI Cards
# ------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
with col1:
    total_markets = df_snap["market_id"].nunique()
    st.metric("Markets Tracked", total_markets)
with col2:
    arb_count = len(df_arb)
    st.metric("Arb Opportunities Today", arb_count)
with col3:
    avg_spread = df_arb["spread"].mean() * 100 if not df_arb.empty else 0
    st.metric("Avg Spread", f"{avg_spread:.1f}%")
with col4:
    latest_date = df_snap["snapshot_date"].max().date() if not df_snap.empty else date.today()
    st.metric("Latest Data", latest_date)

st.divider()

# ------------------------------------------------------------------
# Row 1: Price trends + Volume
# ------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Yes-Price Trends (Equity Indices)")
    equity_df = df_snap[df_snap["question"].str.contains("SPY|SPX|QQQ", case=False, na=False)]
    if not equity_df.empty:
        fig = px.line(
            equity_df,
            x="snapshot_date",
            y="yes_price",
            color="question",
            markers=True,
            labels={"yes_price": "Implied Probability (Yes)", "snapshot_date": "Date"},
        )
        fig.update_layout(height=350, legend=dict(orientation="h", yanchor="bottom", y=-0.35))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No equity index data yet.")

with right:
    st.subheader("Volume by Platform")
    vol_df = df_snap.groupby(["snapshot_date", "platform"])["volume"].sum().reset_index()
    if not vol_df.empty:
        fig = px.bar(
            vol_df,
            x="snapshot_date",
            y="volume",
            color="platform",
            barmode="group",
            labels={"volume": "Daily Volume ($)", "snapshot_date": "Date"},
        )
        fig.update_layout(height=350, legend=dict(orientation="h", yanchor="bottom", y=-0.25))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No volume data yet.")

st.divider()

# ------------------------------------------------------------------
# Row 2: Arbitrage table + Whale concentration
# ------------------------------------------------------------------
left2, right2 = st.columns(2)

with left2:
    st.subheader("Cross-Market Arbitrage (Spread > 5%)")
    if not df_arb.empty:
        df_arb["poly_price"] = df_arb["poly_price"].apply(lambda x: f"{x:.2f}")
        df_arb["kalshi_price"] = df_arb["kalshi_price"].apply(lambda x: f"{x:.2f}")
        df_arb["spread"] = df_arb["spread"].apply(lambda x: f"{x*100:.1f}%")
        st.dataframe(df_arb, use_container_width=True, hide_index=True)
    else:
        st.info("No arbitrage opportunities found today.")

with right2:
    st.subheader("Whale Concentration (Top-5 Wallet %)")
    df_whales = _demo_whales() if USE_DEMO else pd.DataFrame()
    if not df_whales.empty:
        fig = px.bar(
            df_whales.sort_values("top5_pct", ascending=True),
            x="top5_pct",
            y="question",
            orientation="h",
            color="top5_pct",
            color_continuous_scale="Reds",
            labels={"top5_pct": "Top-5 Wallet Volume %", "question": ""},
        )
        fig.update_layout(height=350, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No trade data yet (run fetcher for a few days).")

st.divider()

# ------------------------------------------------------------------
# Row 3: Correlation heatmap (Polymarket vs Kalshi same event)
# ------------------------------------------------------------------
st.subheader("Platform Price Correlation (Same Event)")

pivot = df_snap.pivot_table(index="snapshot_date", columns="question", values="yes_price")
# Keep only questions that appear on both platforms
col_counts = df_snap.groupby("question")["platform"].nunique()
dual_questions = col_counts[col_counts >= 2].index.tolist()
if dual_questions:
    corr_data = []
    for q in dual_questions:
        sub = df_snap[df_snap["question"] == q][["snapshot_date", "platform", "yes_price"]]
        sub_pivot = sub.pivot(index="snapshot_date", columns="platform", values="yes_price")
        if "polymarket" in sub_pivot.columns and "kalshi" in sub_pivot.columns:
            corr = sub_pivot["polymarket"].corr(sub_pivot["kalshi"])
            corr_data.append({"question": q, "correlation": corr})
    if corr_data:
        corr_df = pd.DataFrame(corr_data).sort_values("correlation", ascending=False)
        fig = px.bar(
            corr_df,
            x="correlation",
            y="question",
            orientation="h",
            color="correlation",
            color_continuous_scale="RdYlGn",
            range_color=[0, 1],
            labels={"correlation": "Pearson r", "question": ""},
        )
        fig.update_layout(height=300 + len(corr_df) * 30, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Need at least 2 overlapping days of data to compute correlation.")
else:
    st.info("Need overlapping markets on both platforms to compute correlation.")

if conn:
    conn.close()
