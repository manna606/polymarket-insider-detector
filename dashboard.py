"""
Polymarket + Kalshi Alpha Dashboard — Premium AI Edition
============================================================
Dark-themed, terminal-inspired interface for institutional-grade
prediction market analytics.
============================================================
"""

import os
import json
import random
from datetime import date, timedelta
from typing import List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from local_db import get_db_conn, is_sqlite

# ------------------------------------------------------------------
# Page Config & Global Dark Theme
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Alpha Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Dark theme CSS injection
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@300;400;600;800&display=swap');

    :root {
        --bg-primary: #0a0e1a;
        --bg-card: #111827;
        --bg-elevated: #1a2236;
        --border: #1f2937;
        --text-primary: #f3f4f6;
        --text-secondary: #9ca3af;
        --accent-cyan: #06b6d4;
        --accent-purple: #8b5cf6;
        --accent-green: #10b981;
        --accent-red: #ef4444;
        --accent-orange: #f59e0b;
    }

    .stApp {
        background-color: var(--bg-primary) !important;
        font-family: 'Inter', sans-serif !important;
    }

    h1, h2, h3, h4 {
        font-family: 'Inter', sans-serif !important;
        color: var(--text-primary) !important;
        letter-spacing: -0.02em;
    }

    /* Custom metric cards */
    div[data-testid="metric-container"] {
        background: linear-gradient(145deg, #1a2236, #111827) !important;
        border: 1px solid #374151 !important;
        border-radius: 12px !important;
        padding: 20px !important;
        box-shadow: 0 0 15px rgba(6, 182, 212, 0.15) !important;
    }

    div[data-testid="metric-container"] label {
        color: #9ca3af !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
    }

    div[data-testid="metric-container"] > div {
        color: #f3f4f6 !important;
    }

    div[data-testid="metric-container"] > div > div {
        color: #06b6d4 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 800 !important;
        font-size: 1.6rem !important;
        text-shadow: 0 0 10px rgba(6, 182, 212, 0.4) !important;
    }

    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: transparent !important;
    }

    .stTabs [data-baseweb="tab"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px 8px 0 0 !important;
        color: var(--text-secondary) !important;
        font-weight: 600 !important;
        padding: 12px 24px !important;
        transition: all 0.2s ease;
    }

    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(90deg, var(--accent-purple), var(--accent-cyan)) !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 0 20px rgba(139, 92, 246, 0.3) !important;
    }

    .stTabs [data-baseweb="tab-panel"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 0 12px 12px 12px !important;
        padding: 24px !important;
    }

    /* Info/Warning/Success boxes */
    .stAlert {
        background: var(--bg-elevated) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }

    /* Dataframes */
    .stDataFrame {
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }

    /* Expander */
    .streamlit-expanderHeader {
        background: var(--bg-elevated) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
    }

    /* Divider */
    hr {
        border-color: var(--border) !important;
        opacity: 0.5 !important;
    }

    /* Caption */
    .stCaption {
        color: var(--text-secondary) !important;
        font-size: 0.85rem !important;
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Category Theme Map
# ------------------------------------------------------------------
CATEGORY_THEME = {
    "Politics": {"icon": "🏛️", "color": "#8b5cf6", "desc": "Political events & elections"},
    "Elections": {"icon": "🗳️", "color": "#a78bfa", "desc": "Electoral outcomes"},
    "Economics": {"icon": "📊", "color": "#10b981", "desc": "Markets, Fed, GDP"},
    "World": {"icon": "🌍", "color": "#06b6d4", "desc": "Geopolitical events"},
    "Financials": {"icon": "💰", "color": "#f59e0b", "desc": "Stocks & indices"},
    "Companies": {"icon": "🏢", "color": "#3b82f6", "desc": "Corporate events"},
    "Entertainment": {"icon": "🎬", "color": "#ec4899", "desc": "Pop culture"},
    "Sports": {"icon": "⚽", "color": "#f97316", "desc": "Athletic events"},
    "Crypto": {"icon": "₿", "color": "#fbbf24", "desc": "Digital assets"},
    "Climate and Weather": {"icon": "🌡️", "color": "#ef4444", "desc": "Environmental"},
    "Science and Technology": {"icon": "🔬", "color": "#06b6d4", "desc": "Tech & science"},
    "Social": {"icon": "👥", "color": "#8b5cf6", "desc": "Social trends"},
    "Health": {"icon": "🏥", "color": "#ef4444", "desc": "Medical events"},
    "Transportation": {"icon": "✈️", "color": "#3b82f6", "desc": "Infrastructure"},
    "Equity": {"icon": "📈", "color": "#10b981", "desc": "Stock predictions"},
}


def get_cat_badge(cat: str) -> str:
    theme = CATEGORY_THEME.get(cat, {"icon": "📌", "color": "#9ca3af", "desc": "General"})
    return f"<span style='color:{theme['color']}; font-weight:600;'>\n        {theme['icon']} {cat}\n    </span>"


# ------------------------------------------------------------------
# Demo Data
# ------------------------------------------------------------------
def _demo_df() -> pd.DataFrame:
    return pd.DataFrame([
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
    ])


# ------------------------------------------------------------------
# Data Loaders
# ------------------------------------------------------------------
def load_markets(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.platform, m.question, m.category, m.volume,
               m.outcome_prices, m.end_date
        FROM markets m
        ORDER BY m.volume DESC
    """)
    rows = cur.fetchall()
    cur.close()

    data = []
    for mid, platform, question, category, volume, prices_json, end_date in rows:
        try:
            prices = json.loads(prices_json) if prices_json else []
            yes_price = float(prices[0]) if prices else 0
        except Exception:
            yes_price = 0
        data.append({
            "id": mid, "platform": platform, "question": question,
            "category": category or "Other", "volume": float(volume or 0),
            "yes_price": yes_price, "end_date": end_date,
        })
    return pd.DataFrame(data)


def load_snapshots(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute("""
        SELECT s.market_id, s.snapshot_date, s.outcome_prices, s.volume,
               m.platform, m.question, m.category
        FROM price_snapshots s
        JOIN markets m ON m.id = s.market_id
        ORDER BY s.snapshot_date
    """)
    rows = cur.fetchall()
    cur.close()

    data = []
    for market_id, snap_date, prices_json, volume, platform, question, category in rows:
        try:
            prices = json.loads(prices_json) if prices_json else []
            yes_price = float(prices[0]) if prices else 0
        except Exception:
            yes_price = 0
        data.append({
            "market_id": market_id, "snapshot_date": pd.to_datetime(snap_date),
            "yes_price": yes_price, "volume": float(volume or 0),
            "platform": platform, "question": question,
            "category": category or "Other",
        })
    return pd.DataFrame(data)


def load_arb(conn) -> pd.DataFrame:
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT event_name, poly_price_yes, kalshi_price_yes, spread
            FROM arbitrage_opps
            WHERE snapshot_date = date('now')
            ORDER BY spread DESC
        """)
        rows = cur.fetchall()
        cur.close()
        return pd.DataFrame(rows, columns=["event_name", "poly_price", "kalshi_price", "spread"])
    except Exception:
        cur.close()
        return pd.DataFrame()


# ------------------------------------------------------------------
# Header
# ------------------------------------------------------------------
col_logo, col_title = st.columns([0.15, 0.85])
with col_logo:
    st.markdown("<div style='font-size:3rem; text-align:center;'>⚡</div>", unsafe_allow_html=True)
with col_title:
    st.markdown("""
        <h1 style='margin:0; font-weight:800; background: linear-gradient(90deg, #06b6d4, #8b5cf6);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
            Alpha Terminal
        </h1>
        <p style='margin:0; color:#6b7280; font-size:1rem; font-weight:300;'>
            Polymarket + Kalshi Intelligence Layer
        </p>
    """, unsafe_allow_html=True)

st.divider()

# ------------------------------------------------------------------
# Load Data
# ------------------------------------------------------------------
conn = get_db_conn()
if conn:
    df_markets = load_markets(conn)
    df_snap = load_snapshots(conn)
    df_arb = load_arb(conn)
    USE_DEMO = df_markets.empty
    if USE_DEMO:
        st.info("🔗 Connected to Railway DB — populating with demo data until fetcher runs.")
        df_markets = _demo_df()
        df_snap = _demo_df().assign(snapshot_date=pd.Timestamp(date.today()))
else:
    st.warning("🔌 Database offline — showing demo data.")
    df_markets = _demo_df()
    df_snap = _demo_df().assign(snapshot_date=pd.Timestamp(date.today()))
    df_arb = pd.DataFrame()
    USE_DEMO = True

# ------------------------------------------------------------------
# KPI Cards
# ------------------------------------------------------------------
st.markdown("<h3 style='color:#9ca3af; font-weight:600; margin-bottom:1rem;'>📊 MARKET PULSE</h3>", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
with k1:
    poly_vol = df_snap[df_snap["platform"] == "polymarket"]["volume"].sum()
    st.metric("Polymarket Vol", f"${poly_vol/1e6:.1f}M" if poly_vol else "$0")
with k2:
    kal_vol = df_snap[df_snap["platform"] == "kalshi"]["volume"].sum()
    st.metric("Kalshi Vol", f"${kal_vol/1e6:.1f}M" if kal_vol else "$0")
with k3:
    st.metric("Active Markets", len(df_markets))
with k4:
    st.metric("Arb Signals", len(df_arb))

st.divider()

# ------------------------------------------------------------------
# Tabs
# ------------------------------------------------------------------
tab_poly, tab_kalshi, tab_arb, tab_insights = st.tabs([
    "🟣  Polymarket", "🔵  Kalshi", "⚡  Arbitrage", "📈  Insights"
])

# ---------- Polymarket ----------
with tab_poly:
    st.markdown("<h2 style='color:#8b5cf6;'>Polymarket</h2>", unsafe_allow_html=True)
    st.caption("Crypto-native. Higher volume. Global liquidity.")

    poly = df_markets[df_markets["platform"] == "polymarket"].sort_values("volume", ascending=False)
    if not poly.empty:
        for _, row in poly.iterrows():
            price = row["yes_price"]
            color = "#10b981" if price > 0.6 else "#f59e0b" if price > 0.4 else "#ef4444"
            vol = f"${row['volume']/1e6:.2f}M" if row["volume"] >= 1e6 else f"${row['volume']:,.0f}"

            st.markdown(f"""
            <div style='background: linear-gradient(90deg, rgba(139,92,246,0.1), transparent);
                border-left: 3px solid #8b5cf6; padding: 16px 20px; border-radius: 8px;
                margin-bottom: 12px;'>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <div style='flex:1;'>
                        <div style='font-size:1.1rem; font-weight:600; color:#f3f4f6; margin-bottom:4px;'>
                            {row['question'][:70]}
                        </div>
                        <div style='font-size:0.85rem;'>{get_cat_badge(row['category'])}</div>
                    </div>
                    <div style='text-align:right; margin-left:24px;'>
                        <div style='font-size:1.6rem; font-weight:700; color:{color}; font-family:"JetBrains Mono",monospace;'>
                            {price:.0%}
                        </div>
                        <div style='font-size:0.75rem; color:#6b7280;'>Yes Price</div>
                    </div>
                    <div style='text-align:right; margin-left:24px; min-width:100px;'>
                        <div style='font-size:1.1rem; font-weight:600; color:#f3f4f6;'>{vol}</div>
                        <div style='font-size:0.75rem; color:#6b7280;'>Volume</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Donut chart
        cat_df = poly.groupby("category").agg({"volume": "sum"}).reset_index()
        fig = px.pie(cat_df, values="volume", names="category", hole=0.6,
                     color_discrete_sequence=px.colors.sequential.Plasma_r)
        fig.update_traces(textinfo="label+percent", textposition="outside",
                          textfont=dict(color="#9ca3af"))
        fig.update_layout(
            showlegend=False, height=320,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ca3af"),
            annotations=[dict(text="Sectors", x=0.5, y=0.5, font_size=16,
                              showarrow=False, font_color="#f3f4f6")]
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No Polymarket data today.")


# ---------- Kalshi ----------
with tab_kalshi:
    st.markdown("<h2 style='color:#06b6d4;'>Kalshi</h2>", unsafe_allow_html=True)
    st.caption("Regulated US exchange. Politics & economics focus.")

    kal = df_markets[df_markets["platform"] == "kalshi"].sort_values("volume", ascending=False)
    if not kal.empty:
        for _, row in kal.iterrows():
            price = row["yes_price"]
            color = "#10b981" if price > 0.6 else "#f59e0b" if price > 0.4 else "#ef4444"
            vol = f"${row['volume']/1e6:.2f}M" if row["volume"] >= 1e6 else f"${row['volume']:,.0f}"

            st.markdown(f"""
            <div style='background: linear-gradient(90deg, rgba(6,182,212,0.1), transparent);
                border-left: 3px solid #06b6d4; padding: 16px 20px; border-radius: 8px;
                margin-bottom: 12px;'>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <div style='flex:1;'>
                        <div style='font-size:1.1rem; font-weight:600; color:#f3f4f6; margin-bottom:4px;'>
                            {row['question'][:70]}
                        </div>
                        <div style='font-size:0.85rem;'>{get_cat_badge(row['category'])}</div>
                    </div>
                    <div style='text-align:right; margin-left:24px;'>
                        <div style='font-size:1.6rem; font-weight:700; color:{color}; font-family:"JetBrains Mono",monospace;'>
                            {price:.0%}
                        </div>
                        <div style='font-size:0.75rem; color:#6b7280;'>Yes Price</div>
                    </div>
                    <div style='text-align:right; margin-left:24px; min-width:100px;'>
                        <div style='font-size:1.1rem; font-weight:600; color:#f3f4f6;'>{vol}</div>
                        <div style='font-size:0.75rem; color:#6b7280;'>Volume</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        cat_df = kal.groupby("category").agg({"volume": "sum"}).reset_index()
        fig = px.pie(cat_df, values="volume", names="category", hole=0.6,
                     color_discrete_sequence=px.colors.sequential.Cividis_r)
        fig.update_traces(textinfo="label+percent", textposition="outside",
                          textfont=dict(color="#9ca3af"))
        fig.update_layout(
            showlegend=False, height=320,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ca3af"),
            annotations=[dict(text="Sectors", x=0.5, y=0.5, font_size=16,
                              showarrow=False, font_color="#f3f4f6")]
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No Kalshi data today.")


# ---------- Arbitrage ----------
with tab_arb:
    st.markdown("<h2 style='color:#f59e0b;'>Cross-Market Arbitrage</h2>", unsafe_allow_html=True)
    st.caption("Price divergence signals between Polymarket and Kalshi.")

    if not df_arb.empty:
        for _, row in df_arb.iterrows():
            spread = row["spread"]
            pct = spread * 100
            if spread > 0.15:
                severity, glow = "🔴 HIGH", "rgba(239,68,68,0.2)"
                border = "#ef4444"
            elif spread > 0.08:
                severity, glow = "🟠 MEDIUM", "rgba(245,158,11,0.2)"
                border = "#f59e0b"
            else:
                severity, glow = "🟢 LOW", "rgba(16,185,129,0.2)"
                border = "#10b981"

            st.markdown(f"""
            <div style='background: linear-gradient(135deg, {glow}, transparent);
                border: 1px solid {border}; padding: 24px; border-radius: 12px;
                margin-bottom: 16px; box-shadow: 0 0 30px {glow};'>
                <div style='font-size:0.85rem; color:{border}; font-weight:700; margin-bottom:8px;'>
                    {severity}
                </div>
                <div style='font-size:1.2rem; font-weight:600; color:#f3f4f6; margin-bottom:16px;'>
                    {row['event_name'][:60]}
                </div>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <div style='text-align:center;'>
                        <div style='font-size:0.8rem; color:#9ca3af; margin-bottom:4px;'>Polymarket</div>
                        <div style='font-size:2rem; font-weight:700; color:#8b5cf6; font-family:"JetBrains Mono",monospace;'>
                            {row['poly_price']:.0%}
                        </div>
                    </div>
                    <div style='font-size:1.5rem; color:#4b5563;'>vs</div>
                    <div style='text-align:center;'>
                        <div style='font-size:0.8rem; color:#9ca3af; margin-bottom:4px;'>Kalshi</div>
                        <div style='font-size:2rem; font-weight:700; color:#06b6d4; font-family:"JetBrains Mono",monospace;'>
                            {row['kalshi_price']:.0%}
                        </div>
                    </div>
                    <div style='text-align:center; margin-left:auto; padding-left:40px;'>
                        <div style='font-size:0.8rem; color:#9ca3af; margin-bottom:4px;'>Spread</div>
                        <div style='font-size:2.2rem; font-weight:800; color:{border}; font-family:"JetBrains Mono",monospace;'>
                            {pct:.1f}%
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("💡 Analysis"):
                st.markdown(f"""
                **Signal:** {severity} divergence detected.

                - **Long bias:** If true probability ≈ {row['poly_price']:.0%}, Kalshi is undervalued.
                - **Short bias:** If true probability ≈ {row['kalshi_price']:.0%}, Polymarket is overvalued.
                - **Est. profit / $1k:** ~${spread*1000:.0f} (before fees & slippage)

                ⚠️ Verify that both markets reference the **identical** underlying event before executing.
                """)
    else:
        st.markdown("""
        <div style='text-align:center; padding:60px 20px; color:#6b7280;'>
            <div style='font-size:3rem; margin-bottom:16px;'>✅</div>
            <div style='font-size:1.2rem; font-weight:600;'>No Arb Signals Today</div>
            <div style='font-size:0.9rem;'>All tracked markets show &lt;5% cross-platform divergence.</div>
        </div>
        """, unsafe_allow_html=True)

    # Volume comparison
    st.subheader("Platform Volume Comparison")
    vdf = pd.DataFrame([
        {"Platform": "Polymarket", "Volume": poly_vol, "color": "#8b5cf6"},
        {"Platform": "Kalshi", "Volume": kal_vol, "color": "#06b6d4"},
    ])
    fig = px.bar(vdf, x="Platform", y="Volume", color="Platform",
                 color_discrete_map={"Polymarket": "#8b5cf6", "Kalshi": "#06b6d4"},
                 text=vdf["Volume"].apply(lambda x: f"${x/1e6:.1f}M" if x >= 1e6 else f"${x:,.0f}"))
    fig.update_traces(textposition="outside", marker_line_width=0)
    fig.update_layout(showlegend=False, height=350,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#9ca3af"), yaxis_gridcolor="#1f2937",
                      xaxis_linecolor="#1f2937")
    st.plotly_chart(fig, use_container_width=True)


# ---------- Insights ----------
with tab_insights:
    st.markdown("<h2 style='color:#10b981;'>Market Intelligence</h2>", unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Sector Heatmap")
        if not df_markets.empty:
            cdf = df_markets.groupby("category").agg({"volume": "sum", "question": "count"}).reset_index()
            cdf.columns = ["category", "volume", "count"]
            fig = px.treemap(
                cdf, path=["category"], values="volume", color="volume",
                color_continuous_scale="Viridis", custom_data=["count"], height=400
            )
            fig.update_traces(
                hovertemplate='<b>%{label}</b><br>Vol: $%{value:,.0f}<br>Markets: %{customdata[0]}',
                texttemplate='%{label}<br>$%{value:,.0f}', textfont=dict(color="white")
            )
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Whale Concentration")
        st.info("Requires 3+ days of trade history. Run fetcher daily to populate.")

    st.divider()
    st.caption(f"Alpha Terminal v1.0  |  Data: {date.today()}  |  QuantSignals Research")

if conn:
    conn.close()
