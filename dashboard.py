"""
Polymarket + Kalshi Alpha Dashboard
============================================================
Interactive Streamlit dashboard for visualising:
  - Daily price snapshots
  - Volume trends
  - Cross-market arbitrage opportunities
  - Whale concentration

Usage (local):
    streamlit run dashboard.py
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

from local_db import get_db_conn, is_sqlite

# ------------------------------------------------------------------
# Category descriptions
# ------------------------------------------------------------------
CATEGORY_INFO = {
    "Politics": {"emoji": "🏛️", "desc": "Political events, elections, government actions"},
    "Elections": {"emoji": "🗳️", "desc": "Voting outcomes and electoral predictions"},
    "Economics": {"emoji": "📊", "desc": "Fed policy, jobs, GDP, markets"},
    "World": {"emoji": "🌍", "desc": "International affairs and geopolitics"},
    "Financials": {"emoji": "💰", "desc": "Stocks, indices, financial instruments"},
    "Companies": {"emoji": "🏢", "desc": "Corporate events, IPOs, M&A"},
    "Entertainment": {"emoji": "🎬", "desc": "Celebrity, music, movies, pop culture"},
    "Sports": {"emoji": "⚽", "desc": "Games, championships, athlete performance"},
    "Crypto": {"emoji": "₿", "desc": "Bitcoin, Ethereum, digital assets"},
    "Climate and Weather": {"emoji": "🌡️", "desc": "Temperature, disasters"},
    "Science and Technology": {"emoji": "🔬", "desc": "AI, space, tech breakthroughs"},
    "Social": {"emoji": "👥", "desc": "Social trends and culture"},
    "Health": {"emoji": "🏥", "desc": "Pandemics, vaccines, medicine"},
    "Transportation": {"emoji": "✈️", "desc": "Airlines, EVs, infrastructure"},
    "Equity": {"emoji": "📈", "desc": "Stock index predictions (SPY, SPX, QQQ)"},
}


def get_category_badge(category: str) -> str:
    info = CATEGORY_INFO.get(category, {"emoji": "📌", "desc": "General"})
    return f"{info['emoji']} **{category}**"


# ------------------------------------------------------------------
# Demo data
# ------------------------------------------------------------------
def _demo_dates(days: int = 14) -> List[date]:
    today = date.today()
    return [today - timedelta(days=i) for i in range(days, 0, -1)]


def _demo_markets() -> pd.DataFrame:
    markets = [
        {"id": 1, "platform": "polymarket", "question": "Will Jesus Christ return before GTA VI?", "category": "Entertainment", "volume": 11208259, "yes_price": 0.02},
        {"id": 2, "platform": "polymarket", "question": "Russia-Ukraine Ceasefire before GTA VI?", "category": "World", "volume": 1655969, "yes_price": 0.35},
        {"id": 3, "platform": "polymarket", "question": "New Playboi Carti Album before GTA VI?", "category": "Entertainment", "volume": 732298, "yes_price": 0.48},
        {"id": 4, "platform": "polymarket", "question": "New Rihanna Album before GTA VI?", "category": "Entertainment", "volume": 705938, "yes_price": 0.22},
        {"id": 5, "platform": "polymarket", "question": "Trump out as President before GTA VI?", "category": "Politics", "volume": 633483, "yes_price": 0.52},
        {"id": 6, "platform": "kalshi", "question": "Will US take control of any part of Greenland?", "category": "Politics", "volume": 951670, "yes_price": 0.25},
        {"id": 7, "platform": "kalshi", "question": "How much will US acquire Greenland for?", "category": "Politics", "volume": 552664, "yes_price": 0.55},
        {"id": 8, "platform": "kalshi", "question": "Will Trump be impeached and removed from office?", "category": "Politics", "volume": 446681, "yes_price": 0.25},
        {"id": 9, "platform": "kalshi", "question": "Will US acquire any new territory?", "category": "Politics", "volume": 304042, "yes_price": 0.30},
        {"id": 10, "platform": "kalshi", "question": "Will Trump resign during his term?", "category": "Politics", "volume": 196763, "yes_price": 0.25},
    ]
    return pd.DataFrame(markets)


def _demo_arb() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_name": "Trump out as President before GTA VI?", "poly_price": 0.52, "kalshi_price": 0.25, "spread": 0.27, "category": "Politics"},
    ])


def _demo_whales() -> pd.DataFrame:
    return pd.DataFrame([
        {"question": "Will Jesus Christ return before GTA VI?", "top5_pct": 82.5, "total_vol": 5800000},
        {"question": "Trump out as President before GTA VI?", "top5_pct": 45.0, "total_vol": 1450000},
    ])


# ------------------------------------------------------------------
# Data loaders
# ------------------------------------------------------------------
def load_snapshots(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.market_id, s.snapshot_date, s.outcome_prices, s.volume,
               m.platform, m.question, m.category
        FROM price_snapshots s
        JOIN markets m ON m.id = s.market_id
        ORDER BY s.snapshot_date
        """
    )
    rows = cur.fetchall()
    cur.close()

    data = []
    for market_id, snap_date, prices_json, volume, platform, question, category in rows:
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
            "category": category or "Other",
        })
    return pd.DataFrame(data)


def load_today_markets(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.id, m.platform, m.question, m.category, m.volume, m.liquidity,
               m.outcome_prices, m.end_date
        FROM markets m
        WHERE m.updated_at >= date('now')
           OR m.id IN (SELECT market_id FROM price_snapshots WHERE snapshot_date = date('now'))
        ORDER BY m.volume DESC
        """
    )
    rows = cur.fetchall()
    cur.close()

    data = []
    for mid, platform, question, category, volume, liquidity, prices_json, end_date in rows:
        try:
            prices = prices_json if isinstance(prices_json, list) else json.loads(prices_json)
            yes_price = float(prices[0]) if prices else 0
        except Exception:
            yes_price = 0
        data.append({
            "id": mid,
            "platform": platform,
            "question": question,
            "category": category or "Other",
            "volume": float(volume or 0),
            "liquidity": float(liquidity or 0),
            "yes_price": yes_price,
            "end_date": end_date,
        })
    return pd.DataFrame(data)


def load_arbitrage(conn) -> pd.DataFrame:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT event_name, poly_price_yes, kalshi_price_yes, spread
            FROM arbitrage_opps
            WHERE snapshot_date = date('now')
            ORDER BY spread DESC
            """
        )
        rows = cur.fetchall()
        cur.close()
        return pd.DataFrame(rows, columns=["event_name", "poly_price", "kalshi_price", "spread"])
    except Exception:
        cur.close()
        return pd.DataFrame()


# ------------------------------------------------------------------
# UI
# ------------------------------------------------------------------
st.set_page_config(page_title="Alpha Dashboard", layout="wide")

st.title("Polymarket + Kalshi Alpha Dashboard")
st.caption("Daily prediction-market data for alpha validation")

# ------------------------------------------------------------------
# Load data
# ------------------------------------------------------------------
conn = get_db_conn()
if conn:
    df_snap = load_snapshots(conn)
    df_today = load_today_markets(conn)
    df_arb = load_arbitrage(conn)
    USE_DEMO = df_snap.empty and df_today.empty
    if USE_DEMO:
        st.info("Database is empty — showing demo data until fetcher populates it.")
        df_snap = _demo_markets().assign(snapshot_date=pd.Timestamp(date.today()))
        df_today = _demo_markets()
        df_arb = _demo_arb()
else:
    st.error("Could not connect to any database.")
    df_snap = _demo_markets().assign(snapshot_date=pd.Timestamp(date.today()))
    df_today = _demo_markets()
    df_arb = _demo_arb()
    USE_DEMO = True

# ------------------------------------------------------------------
# KPI Row
# ------------------------------------------------------------------
ck1, ck2, ck3, ck4, ck5 = st.columns(5)
with ck1:
    st.metric("Markets Tracked", len(df_today))
with ck2:
    poly_vol = df_snap[df_snap["platform"] == "polymarket"]["volume"].sum()
    st.metric("Polymarket Vol", f"${poly_vol/1e6:.1f}M" if poly_vol >= 1e6 else f"${poly_vol:,.0f}")
with ck3:
    kal_vol = df_snap[df_snap["platform"] == "kalshi"]["volume"].sum()
    st.metric("Kalshi Vol", f"${kal_vol/1e6:.1f}M" if kal_vol >= 1e6 else f"${kal_vol:,.0f}")
with ck4:
    st.metric("Arb Signals", len(df_arb))
with ck5:
    st.metric("Data Date", str(date.today()))

st.divider()

# ------------------------------------------------------------------
# Platform Tabs
# ------------------------------------------------------------------
tab_poly, tab_kalshi, tab_arb, tab_insights = st.tabs([
    "🟣 Polymarket",
    "🔵 Kalshi",
    "⚡ Arbitrage Radar",
    "📊 Market Insights"
])

# ---------- Polymarket Tab ----------
with tab_poly:
    st.header("Polymarket — Crypto-based Prediction Market")
    st.caption("Higher volume, broader topics, global audience")

    poly_df = df_today[df_today["platform"] == "polymarket"].sort_values("volume", ascending=False)

    if not poly_df.empty:
        # Market cards
        for _, row in poly_df.iterrows():
            price = row['yes_price']
            price_color = "#2ca02c" if price > 0.6 else "#ff7f0e" if price > 0.4 else "#d62728"
            vol_str = f"${row['volume']/1e6:.2f}M" if row['volume'] >= 1e6 else f"${row['volume']:,.0f}"

            with st.container():
                c1, c2, c3 = st.columns([4, 1.5, 1.5])
                with c1:
                    st.markdown(f"**{row['question'][:70]}**")
                    st.caption(get_category_badge(row['category']))
                with c2:
                    st.markdown(f"<span style='color:{price_color};font-size:1.4rem;font-weight:bold;'>{price:.0%}</span>", unsafe_allow_html=True)
                    st.caption("Yes Probability")
                with c3:
                    st.markdown(f"**{vol_str}**")
                    st.caption("Volume")
                st.markdown("---")

        # Category breakdown chart
        st.subheader("Category Breakdown")
        cat_df = poly_df.groupby("category").agg({"volume": "sum", "question": "count"}).reset_index()
        cat_df.columns = ["category", "volume", "count"]
        fig = px.pie(cat_df, values="volume", names="category", hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_traces(textinfo="label+percent", textposition="outside")
        fig.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No Polymarket data today.")


# ---------- Kalshi Tab ----------
with tab_kalshi:
    st.header("Kalshi — Regulated US Prediction Market")
    st.caption("Politics & economics focus, regulated exchange, US audience")

    kal_df = df_today[df_today["platform"] == "kalshi"].sort_values("volume", ascending=False)

    if not kal_df.empty:
        # Market cards
        for _, row in kal_df.iterrows():
            price = row['yes_price']
            price_color = "#2ca02c" if price > 0.6 else "#ff7f0e" if price > 0.4 else "#d62728"
            vol_str = f"${row['volume']/1e6:.2f}M" if row['volume'] >= 1e6 else f"${row['volume']:,.0f}"

            with st.container():
                c1, c2, c3 = st.columns([4, 1.5, 1.5])
                with c1:
                    st.markdown(f"**{row['question'][:70]}**")
                    st.caption(get_category_badge(row['category']))
                with c2:
                    st.markdown(f"<span style='color:{price_color};font-size:1.4rem;font-weight:bold;'>{price:.0%}</span>", unsafe_allow_html=True)
                    st.caption("Yes Probability")
                with c3:
                    st.markdown(f"**{vol_str}**")
                    st.caption("Volume")
                st.markdown("---")

        # Category breakdown chart
        st.subheader("Category Breakdown")
        cat_df = kal_df.groupby("category").agg({"volume": "sum", "question": "count"}).reset_index()
        cat_df.columns = ["category", "volume", "count"]
        fig = px.pie(cat_df, values="volume", names="category", hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_traces(textinfo="label+percent", textposition="outside")
        fig.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No Kalshi data today.")


# ---------- Arbitrage Tab ----------
with tab_arb:
    st.header("Cross-Market Arbitrage Radar")
    st.caption("Events with >5% price difference between platforms")

    if not df_arb.empty:
        for _, row in df_arb.iterrows():
            spread = row["spread"]
            spread_pct = spread * 100

            if spread > 0.15:
                severity, border_color, bg_color = "🔴 HIGH", "#d62728", "#ffebee"
            elif spread > 0.08:
                severity, border_color, bg_color = "🟠 MEDIUM", "#ff7f0e", "#fff3e0"
            else:
                severity, border_color, bg_color = "🟢 LOW", "#2ca02c", "#e8f5e9"

            st.markdown(f"""
            <div style="border-left: 6px solid {border_color}; background-color: {bg_color}; padding: 20px; border-radius: 8px; margin-bottom: 15px;">
                <h3 style="margin:0 0 10px 0;">{severity} — {row['event_name'][:60]}</h3>
                <div style="display:flex; align-items:center; gap:40px;">
                    <div>
                        <div style="font-size:0.9rem; color:#666;">Polymarket</div>
                        <div style="font-size:2rem; font-weight:bold; color:#636EFA;">{row['poly_price']:.0%}</div>
                    </div>
                    <div style="font-size:1.5rem; color:#999;">vs</div>
                    <div>
                        <div style="font-size:0.9rem; color:#666;">Kalshi</div>
                        <div style="font-size:2rem; font-weight:bold; color:#EF553B;">{row['kalshi_price']:.0%}</div>
                    </div>
                    <div style="margin-left:auto;">
                        <div style="font-size:0.9rem; color:#666;">Spread</div>
                        <div style="font-size:2rem; font-weight:bold; color:{border_color};">{spread_pct:.1f}%</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("💡 What this means"):
                st.markdown(f"""
                **Interpretation:**
                - If you think the true probability is closer to **{row['poly_price']:.0%}** (Polymarket), Kalshi is underpriced
                - If you think it's closer to **{row['kalshi_price']:.0%}** (Kalshi), Polymarket is overpriced
                - ⚠️ Make sure the questions are **identical** before trading

                **Potential profit (per $1,000):** ~${spread * 1000:.0f} (before fees)
                """)
    else:
        st.success("✅ No significant arbitrage opportunities found today (spread < 5%)")

    # Platform volume comparison
    st.subheader("Platform Volume Comparison")
    vol_data = []
    for platform in ["polymarket", "kalshi"]:
        vol = df_snap[df_snap["platform"] == platform]["volume"].sum()
        vol_data.append({"Platform": platform.title(), "Volume": vol})
    vol_df = pd.DataFrame(vol_data)
    fig = px.bar(vol_df, x="Platform", y="Volume", color="Platform",
                 color_discrete_map={"Polymarket": "#636EFA", "Kalshi": "#EF553B"},
                 text=vol_df["Volume"].apply(lambda x: f"${x/1e6:.1f}M" if x >= 1e6 else f"${x:,.0f}"))
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, height=350)
    st.plotly_chart(fig, use_container_width=True)


# ---------- Insights Tab ----------
with tab_insights:
    st.header("Market Insights")

    left, right = st.columns(2)

    with left:
        st.subheader("🎯 Market Category Mix")
        if not df_today.empty:
            cat_df = df_today.groupby("category").agg({"volume": "sum", "question": "count"}).reset_index()
            cat_df.columns = ["category", "total_volume", "market_count"]
            fig = px.treemap(
                cat_df, path=["category"], values="total_volume", color="total_volume",
                color_continuous_scale="Blues", custom_data=["market_count"], height=400
            )
            fig.update_traces(
                hovertemplate='<b>%{label}</b><br>Volume: $%{value:,.0f}<br>Markets: %{customdata[0]}',
                texttemplate='%{label}<br>$%{value:,.0f}'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Need data for category breakdown.")

    with right:
        st.subheader("🐋 Whale Concentration")
        df_whales = _demo_whales() if USE_DEMO else pd.DataFrame()
        if not df_whales.empty:
            fig = px.bar(
                df_whales.sort_values("top5_pct", ascending=True),
                x="top5_pct", y="question", orientation="h",
                color="top5_pct", color_continuous_scale="Reds",
                height=400, text=df_whales["top5_pct"].apply(lambda x: f"{x:.1f}%")
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(coloraxis_showscale=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("High concentration (>60%) may suggest insider knowledge")
        else:
            st.info("No trade data yet. Run fetcher for several days.")

    st.divider()
    st.subheader("🔗 Cross-Platform Price Correlation")
    st.caption("How closely do platforms agree on the same event? (needs 2+ days of data)")
    st.info("Correlation analysis requires the same event on both platforms across multiple days. Run fetcher daily to populate.")

# Footer
st.divider()
st.caption(f"📅 Dashboard generated on {date.today()} | Data pipeline: v1.0")

if conn:
    conn.close()
