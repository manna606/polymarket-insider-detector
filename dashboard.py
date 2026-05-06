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

from local_db import get_db_conn, is_sqlite

# ------------------------------------------------------------------
# Category descriptions for non-technical viewers
# ------------------------------------------------------------------
CATEGORY_INFO = {
    "Politics": {"emoji": "🏛️", "desc": "Political events, elections, and government actions"},
    "Elections": {"emoji": "🗳️", "desc": "Voting outcomes and electoral predictions"},
    "Economics": {"emoji": "📊", "desc": "Markets, Fed policy, jobs, and GDP indicators"},
    "World": {"emoji": "🌍", "desc": "International affairs and geopolitical events"},
    "Financials": {"emoji": "💰", "desc": "Stocks, indices (SPY/SPX/QQQ), and financial instruments"},
    "Companies": {"emoji": "🏢", "desc": "Corporate events, IPOs, and M&A"},
    "Entertainment": {"emoji": "🎬", "desc": "Celebrity, music, movies, and pop culture"},
    "Sports": {"emoji": "⚽", "desc": "Games, championships, and athlete performance"},
    "Crypto": {"emoji": "₿", "desc": "Bitcoin, Ethereum, and digital assets"},
    "Climate and Weather": {"emoji": "🌡️", "desc": "Temperature records and natural disasters"},
    "Science and Technology": {"emoji": "🔬", "desc": "AI, space, and scientific breakthroughs"},
    "Social": {"emoji": "👥", "desc": "Social trends and cultural movements"},
    "Health": {"emoji": "🏥", "desc": "Pandemics, vaccines, and medical developments"},
    "Transportation": {"emoji": "✈️", "desc": "Airlines, EVs, and infrastructure"},
    "Equity": {"emoji": "📈", "desc": "Stock index predictions (SPY, SPX, QQQ)"},
}


def get_category_badge(category: str) -> str:
    info = CATEGORY_INFO.get(category, {"emoji": "📌", "desc": "General prediction market"})
    return f"{info['emoji']} **{category}** — {info['desc']}"


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
        {"event_name": "SPY up today?", "poly_price": 0.55, "kalshi_price": 0.61, "spread": 0.06, "poly_question": "SPY up today?", "kalshi_question": "SPY up today?", "category": "Equity"},
        {"event_name": "Trump wins 2024?", "poly_price": 0.42, "kalshi_price": 0.49, "spread": 0.07, "poly_question": "Trump wins 2024?", "kalshi_question": "Trump wins 2024?", "category": "Politics"},
        {"event_name": "Fed cuts in June?", "poly_price": 0.30, "kalshi_price": 0.36, "spread": 0.06, "poly_question": "Fed cuts in June?", "kalshi_question": "Fed cuts in June?", "category": "Economics"},
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
    """Load today's market snapshot with full details."""
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
# Streamlit UI Configuration
# ------------------------------------------------------------------

st.set_page_config(
    page_title="Alpha Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
    }
    .category-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 15px;
        background-color: #f0f2f6;
        color: #333;
        font-size: 0.85rem;
        margin-right: 5px;
    }
    .arb-high {
        color: #d62728;
        font-weight: bold;
    }
    .arb-medium {
        color: #ff7f0e;
        font-weight: bold;
    }
    .arb-low {
        color: #2ca02c;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">Polymarket + Kalshi Alpha Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Daily prediction-market intelligence for alpha validation</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------
# Sidebar with explanations
# ------------------------------------------------------------------
with st.sidebar:
    st.header("📖 How to Read This Dashboard")
    st.markdown("""
    **This dashboard tracks two prediction market platforms:**

    **Polymarket** — Crypto-based, higher volume, broader topics

    **Kalshi** — Regulated US exchange, politics & economics focus

    ---

    **Key Metrics:**
    - **Yes Price**: Probability of event happening (0-1 = 0%-100%)
    - **Volume**: Total money traded (liquidity indicator)
    - **Spread**: Price difference between platforms (arbitrage signal)
    - **Whale Concentration**: % of volume from top 5 wallets

    ---

    **Event Categories:**
    """)
    for cat, info in CATEGORY_INFO.items():
        st.markdown(f"{info['emoji']} **{cat}** — {info['desc']}")

# ------------------------------------------------------------------
# Decide data source
# ------------------------------------------------------------------
conn = get_db_conn()
if conn:
    db_kind = "SQLite (local)" if is_sqlite(conn) else "PostgreSQL"
    df_snap = load_snapshots(conn)
    df_today = load_today_markets(conn)
    df_arb = load_arbitrage(conn)
    USE_DEMO = df_snap.empty
    if USE_DEMO:
        st.info("Database is empty — showing demo data until fetcher populates it.")
        df_snap = _demo_snapshots()
        df_today = _demo_markets()
        df_arb = _demo_arb()
else:
    st.error("Could not connect to any database.")
    df_snap = _demo_snapshots()
    df_today = _demo_markets()
    df_arb = _demo_arb()
    USE_DEMO = True

# ------------------------------------------------------------------
# KPI Cards Row
# ------------------------------------------------------------------
st.subheader("📊 Today's Snapshot")

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

with kpi1:
    total_markets = len(df_today) if not df_today.empty else df_snap["market_id"].nunique()
    st.metric("Markets Tracked", total_markets, help="Total unique markets across both platforms")

with kpi2:
    poly_vol = df_snap[df_snap["platform"] == "polymarket"]["volume"].sum() if not df_snap.empty else 0
    st.metric("Polymarket Volume", f"${poly_vol/1e6:.1f}M" if poly_vol >= 1e6 else f"${poly_vol:,.0f}",
              help="Total trading volume on Polymarket today")

with kpi3:
    kal_vol = df_snap[df_snap["platform"] == "kalshi"]["volume"].sum() if not df_snap.empty else 0
    st.metric("Kalshi Volume", f"${kal_vol/1e6:.1f}M" if kal_vol >= 1e6 else f"${kal_vol:,.0f}",
              help="Total trading volume on Kalshi today")

with kpi4:
    arb_count = len(df_arb)
    st.metric("Arb Opportunities", arb_count,
              help="Markets with >5% price spread between platforms")

with kpi5:
    latest_date = df_snap["snapshot_date"].max().date() if not df_snap.empty else date.today()
    st.metric("Data Date", str(latest_date), help="Latest snapshot date in database")

st.divider()

# ------------------------------------------------------------------
# Section 1: Today's Markets Table (NEW — most requested)
# ------------------------------------------------------------------
st.subheader("📋 Today's Markets by Platform")
st.caption("Complete list of tracked markets with category, price, and volume")

if not df_today.empty:
    # Create display dataframe
    display_df = df_today.copy()
    display_df["yes_price_pct"] = (display_df["yes_price"] * 100).round(1)
    display_df["volume_display"] = display_df["volume"].apply(lambda x: f"${x/1e6:.2f}M" if x >= 1e6 else f"${x:,.0f}")
    display_df["platform_emoji"] = display_df["platform"].map({"polymarket": "🟣", "kalshi": "🔵"})
    display_df["category_badge"] = display_df["category"].apply(
        lambda c: f"{CATEGORY_INFO.get(c, {'emoji': '📌'})['emoji']} {c}"
    )

    # Sort by platform then volume
    display_df = display_df.sort_values(["platform", "volume"], ascending=[True, False])

    # Show as styled table
    for platform in ["polymarket", "kalshi"]:
        platform_df = display_df[display_df["platform"] == platform]
        if not platform_df.empty:
            platform_name = "🟣 Polymarket" if platform == "polymarket" else "🔵 Kalshi"
            with st.expander(f"{platform_name} — {len(platform_df)} markets", expanded=True):
                for _, row in platform_df.iterrows():
                    col1, col2, col3, col4 = st.columns([3, 1.5, 1, 1.2])
                    with col1:
                        st.markdown(f"**{row['question'][:70]}**")
                        st.caption(get_category_badge(row['category']))
                    with col2:
                        # Price gauge
                        price = row['yes_price']
                        color = "#2ca02c" if price > 0.6 else "#ff7f0e" if price > 0.4 else "#d62728"
                        st.markdown(f"<span style='color:{color};font-size:1.3rem;font-weight:bold;'>{price:.0%}</span>", unsafe_allow_html=True)
                        st.caption("Yes Probability")
                    with col3:
                        st.markdown(f"**{row['volume_display']}**")
                        st.caption("Volume")
                    with col4:
                        if pd.notna(row.get('end_date')) and row.get('end_date'):
                            try:
                                end = pd.to_datetime(row['end_date']).strftime('%Y-%m-%d')
                                st.caption(f"⏰ Ends: {end}")
                            except:
                                pass
                    st.markdown("---")
else:
    st.info("No market data available yet. Run `python fetcher.py` to populate.")

st.divider()

# ------------------------------------------------------------------
# Section 2: Price Trends & Volume
# ------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("📈 Yes-Price Trends")
    st.caption("Implied probability of 'Yes' outcome over time")

    # Category filter
    categories = df_snap["category"].dropna().unique().tolist() if not df_snap.empty else []
    if categories:
        selected_cats = st.multiselect("Filter by category:", categories, default=categories[:3] if len(categories) >= 3 else categories)
        filtered_df = df_snap[df_snap["category"].isin(selected_cats)] if selected_cats else df_snap
    else:
        filtered_df = df_snap

    if not filtered_df.empty and len(filtered_df) > 0:
        fig = px.line(
            filtered_df,
            x="snapshot_date",
            y="yes_price",
            color="question",
            facet_col="platform",
            markers=True,
            labels={"yes_price": "Yes Probability", "snapshot_date": "Date"},
            title="",
            height=400,
        )
        fig.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=-0.4, xanchor="center", x=0.5),
            yaxis_tickformat=".0%",
            hovermode="x unified",
        )
        fig.update_traces(line=dict(width=3))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Need 2+ days of data to show trends. Run fetcher daily.")

with right:
    st.subheader("💵 Volume by Platform")
    st.caption("Daily trading volume comparison")

    vol_df = df_snap.groupby(["snapshot_date", "platform"])["volume"].sum().reset_index()
    if not vol_df.empty:
        # Add platform colors
        color_map = {"polymarket": "#636EFA", "kalshi": "#EF553B"}
        fig = px.bar(
            vol_df,
            x="snapshot_date",
            y="volume",
            color="platform",
            barmode="group",
            labels={"volume": "Volume ($)", "snapshot_date": "Date"},
            color_discrete_map=color_map,
            height=400,
        )
        fig.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
            yaxis_tickprefix="$",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No volume data yet.")

st.divider()

# ------------------------------------------------------------------
# Section 3: Arbitrage Opportunities
# ------------------------------------------------------------------
st.subheader("⚡ Cross-Market Arbitrage Radar")
st.caption("Events with price differences >5% between Polymarket and Kalshi")

if not df_arb.empty:
    # Create visual arbitrage cards
    for _, row in df_arb.iterrows():
        spread = row["spread"]
        spread_pct = spread * 100

        # Determine severity
        if spread > 0.15:
            severity = "🔴 HIGH"
            border_color = "#d62728"
            bg_color = "#ffebee"
        elif spread > 0.08:
            severity = "🟠 MEDIUM"
            border_color = "#ff7f0e"
            bg_color = "#fff3e0"
        else:
            severity = "🟢 LOW"
            border_color = "#2ca02c"
            bg_color = "#e8f5e9"

        st.markdown(f"""
        <div style="border-left: 5px solid {border_color}; background-color: {bg_color}; padding: 15px; border-radius: 5px; margin-bottom: 10px;">
            <h4 style="margin:0;">{severity} — {row['event_name'][:60]}</h4>
            <p style="margin:5px 0 0 0;">
                <span style="font-size:1.5rem; font-weight:bold;">🟣 {row['poly_price']:.0%}</span>
                <span style="margin:0 20px;">vs</span>
                <span style="font-size:1.5rem; font-weight:bold;">🔵 {row['kalshi_price']:.0%}</span>
                <span style="margin-left:30px; font-size:1.3rem; color:{border_color}; font-weight:bold;">
                    Spread: {spread_pct:.1f}%
                </span>
            </p>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("💡 What this means"):
            cat = row.get("category", "Unknown")
            info = CATEGORY_INFO.get(cat, {"desc": "Prediction market event"})
            st.markdown(f"""
            **Event Type:** {info['emoji']} {cat} — {info['desc']}

            **Interpretation:**
            - If you believe the true probability is closer to **{row['poly_price']:.0%}** (Polymarket), Kalshi is underpriced
            - If you believe it's closer to **{row['kalshi_price']:.0%}** (Kalshi), Polymarket is overpriced
            - ⚠️ Check if the questions are **exactly identical** before trading

            **Potential profit (per $1,000):** ~${spread * 1000:.0f} (before fees)
            """)
else:
    st.success("✅ No significant arbitrage opportunities found today (spread < 5%)")

st.divider()

# ------------------------------------------------------------------
# Section 4: Category Distribution & Market Depth
# ------------------------------------------------------------------
left2, right2 = st.columns(2)

with left2:
    st.subheader("🎯 Market Category Mix")
    st.caption("What types of events are people betting on?")

    if not df_snap.empty and "category" in df_snap.columns:
        cat_df = df_snap.drop_duplicates(subset=["market_id"]).groupby("category").agg({
            "volume": "sum",
            "market_id": "count"
        }).reset_index()
        cat_df.columns = ["category", "total_volume", "market_count"]

        if not cat_df.empty:
            fig = px.treemap(
                cat_df,
                path=["category"],
                values="total_volume",
                color="total_volume",
                color_continuous_scale="Blues",
                custom_data=["market_count"],
                height=350,
            )
            fig.update_traces(
                hovertemplate='<b>%{label}</b><br>Volume: $%{value:,.0f}<br>Markets: %{customdata[0]}',
                texttemplate='%{label}<br>$%{value:,.0f}',
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Need more data for category breakdown.")

with right2:
    st.subheader("🐋 Whale Concentration")
    st.caption("Markets where top 5 wallets control most volume")

    df_whales = _demo_whales() if USE_DEMO else pd.DataFrame()
    if not df_whales.empty:
        fig = px.bar(
            df_whales.sort_values("top5_pct", ascending=True),
            x="top5_pct",
            y="question",
            orientation="h",
            color="top5_pct",
            color_continuous_scale="Reds",
            labels={"top5_pct": "Top-5 Wallet %", "question": ""},
            height=350,
            text=df_whales["top5_pct"].apply(lambda x: f"{x:.1f}%"),
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(coloraxis_showscale=False, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        st.caption("💡 High concentration (>60%) suggests insider knowledge or coordinated betting")
    else:
        st.info("No trade data yet. Run fetcher for several days to build history.")

st.divider()

# ------------------------------------------------------------------
# Section 5: Platform Correlation
# ------------------------------------------------------------------
st.subheader("🔗 Cross-Platform Price Correlation")
st.caption("How closely do Polymarket and Kalshi agree on the same event?")

if not df_snap.empty:
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

            # Color based on correlation strength
            fig = px.bar(
                corr_df,
                x="correlation",
                y="question",
                orientation="h",
                color="correlation",
                color_continuous_scale="RdYlGn",
                range_color=[0, 1],
                labels={"correlation": "Agreement (0-1)", "question": ""},
                height=300 + len(corr_df) * 40,
                text=corr_df["correlation"].apply(lambda x: f"{x:.2f}"),
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(coloraxis_showscale=True, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

            st.caption("""
            💡 **Reading the chart:**
            - **1.0** = Perfect agreement between platforms
            - **0.5** = Moderate disagreement
            - **<0.3** = Significant divergence (potential alpha opportunity)
            """)
        else:
            st.info("Need 2+ days of overlapping data to compute correlation.")
    else:
        st.info("Need the same event on both platforms to compare.")
else:
    st.info("No data available for correlation analysis.")

# ------------------------------------------------------------------
# Footer
# ------------------------------------------------------------------
st.divider()
st.caption(f"📅 Dashboard generated on {date.today()} | Data pipeline: v1.0 | Contact: QuantSignals Research")

if conn:
    conn.close()
