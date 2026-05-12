"""
Polymarket + Kalshi Alpha Dashboard — Premium AI Edition
============================================================
Dark-themed, terminal-inspired interface for institutional-grade
prediction market analytics.
============================================================
"""

import os
import re
import json
import random
from datetime import date, timedelta
from typing import List, Optional
from collections import defaultdict

import requests
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
    page_title="QS Flow Detector",
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

    /* Hide Streamlit UI chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

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


def infer_category(question: str, fallback: str = "") -> str:
    """Infer category from question text when API category is wrong or missing."""
    q = question.lower()
    # Sports (high confidence keywords)
    if any(k in q for k in [
        "champions league", "world cup", "super bowl", "premier league", "la liga",
        "serie a", "bundesliga", "olympics", "olympic", "top scorer", "goal scorer",
        "win the ucl", "uefa", "fifa", "nba finals", "nfl ", "mlb ", "nhl ",
        "tennis", "grand slam", "wimbledon", "us open", "french open",
        "formula 1", "f1 ", "nascar", "ufc", "boxing", "golf", "pga",
    ]):
        return "Sports"
    # Politics
    if any(k in q for k in [
        "trump", "biden", "election", "president", "impeach", "vote", "congress",
        "senate", "mayoral", "mayor", "governor", "candidate", "primary",
        "parliament", "cabinet", "minister", "policy", "legislation", "ballot",
        "referendum", "nomination", "appoint", "house of", "midterm",
    ]):
        return "Politics"
    # Crypto
    if any(k in q for k in [
        "bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol ",
        "blockchain", "altcoin", "defi", "nft", "token", "stablecoin",
    ]):
        return "Crypto"
    # Financials / Equity
    if any(k in q for k in [
        "spy", "spx", "qqq", "nasdaq", "s&p", "sp500", "index", "stock",
        "share price", "market cap", "ipo ", "merger", "acquisition",
        "earnings", "revenue", "dividend", "blue chip",
    ]):
        return "Financials"
    # Economics
    if any(k in q for k in [
        "fed ", "federal reserve", "interest rate", "gdp", "inflation",
        "recession", "unemployment", "cpi", "ppi", "jobs report", "nonfarm",
        "treasury", "yield", "economy", "economic",
    ]):
        return "Economics"
    # Companies
    if any(k in q for k in [
        "tesla", "apple", "microsoft", "google", "amazon", "nvidia", "meta",
        "netflix", "uber", "airbnb", "disney", "openai", "spacex",
        "company", "corporation", "ceo ", "cfo ", "layoff", "hiring",
    ]):
        return "Companies"
    # Entertainment
    if any(k in q for k in [
        "gta", "grand theft auto", "album", "movie", "oscar", "grammy", "emmy",
        "game", "gaming", "taylor swift", "kanye", "drake", "rihanna",
        "beyonce", "spotify", "disney+", "hbo", "tv show", "series", "box office",
    ]):
        return "Entertainment"
    # Science and Technology
    if any(k in q for k in [
        "ai ", "artificial intelligence", "llm", "gpt", "chatgpt", "robot",
        "space", "mars", "moon landing", "rocket", "satellite", "vaccine",
        "clinical trial", "fda approval", "drug", "crispr", "gene", "fusion", "quantum",
    ]):
        return "Science and Technology"
    # Climate and Weather
    if any(k in q for k in [
        "hurricane", "tornado", "storm", "temperature", "climate", "weather",
        "rainfall", "drought", "wildfire", "flood", "el nino", "la nina",
    ]):
        return "Climate and Weather"
    # World / Geopolitics
    if any(k in q for k in [
        "russia", "ukraine", "china", "israel", "gaza", "iran", "north korea",
        "taiwan", "greenland", "nato", "war", "ceasefire", "invasion",
        "sanction", "embassy", "diplomatic", "treaty", "conflict",
    ]):
        return "World"
    # Health
    if any(k in q for k in [
        "covid", "pandemic", "disease", "virus", "outbreak", "hospital",
        "medicare", "medicaid", "healthcare", "insurance",
    ]):
        return "Health"
    # Transportation
    if any(k in q for k in [
        "flight", "airline", "airport", "boeing", "airbus", "train", "railway",
        "shipping", "port", "traffic", "ev ", "electric vehicle", "autonomous",
    ]):
        return "Transportation"
    # Fallback to API category if valid
    if fallback and fallback in CATEGORY_THEME:
        return fallback
    return "General"


# ------------------------------------------------------------------
# Whale Radar — CLOB Real-Time Integration
# ------------------------------------------------------------------
DATA_API = "https://data-api.polymarket.com"
WHALE_THRESHOLD_USD = 10_000
MEGA_WHALE_THRESHOLD_USD = 100_000


@st.cache_data(ttl=300)
def fetch_clob_trades(condition_id: str, limit: int = 100):
    """Fetch recent CLOB trades for a single market."""
    try:
        resp = requests.get(
            f"{DATA_API}/trades",
            params={"market": condition_id, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def get_polymarket_markets(conn) -> pd.DataFrame:
    """Return active Polymarket markets with their external condition IDs."""
    if not conn:
        return pd.DataFrame()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, external_id, question, slug, category, volume
        FROM markets
        WHERE platform = 'polymarket' AND active = TRUE AND closed = FALSE
        ORDER BY volume DESC
    """)
    rows = cur.fetchall()
    cur.close()
    return pd.DataFrame(
        rows,
        columns=["market_id", "condition_id", "question", "slug", "category", "volume"],
    )


def analyze_whale_activity(all_trades: list):
    """Analyze raw CLOB trades and extract whale alerts + wallet profiles + brief."""
    wallets = defaultdict(lambda: {"trades": [], "total_volume": 0})
    whale_alerts = []

    for t in all_trades:
        wallet = t.get("proxyWallet") or t.get("maker") or "unknown"
        pseudonym = t.get("pseudonym", "Anonymous")
        size = float(t.get("size", 0))
        price = float(t.get("price", 0))
        usd = size * price
        side = t.get("side", "BUY")
        title = t.get("title", "Unknown")

        wallets[wallet]["trades"].append({
            "side": side, "size": size, "price": price,
            "usd": usd, "market": title, "pseudonym": pseudonym,
        })
        wallets[wallet]["total_volume"] += usd

        if usd >= WHALE_THRESHOLD_USD:
            whale_alerts.append({
                "wallet": wallet[:12] + "...",
                "pseudonym": pseudonym,
                "side": side,
                "usd": usd,
                "market": title,
                "type": "MEGA WHALE" if usd >= MEGA_WHALE_THRESHOLD_USD else "WHALE",
                "color": "#ef4444" if usd >= MEGA_WHALE_THRESHOLD_USD else "#f59e0b",
            })

    whale_alerts.sort(key=lambda x: x["usd"], reverse=True)

    # Wallet profiles
    profiles = []
    for wallet, data in wallets.items():
        if data["total_volume"] < 100:
            continue
        trades_list = data["trades"]
        avg_trade = data["total_volume"] / len(trades_list)
        tier = (
            "🐋 MEGA WHALE" if avg_trade >= MEGA_WHALE_THRESHOLD_USD
            else "🐋 WHALE" if avg_trade >= WHALE_THRESHOLD_USD
            else "🦈 Shark" if avg_trade >= 1_000
            else "🐟 Retail"
        )
        profiles.append({
            "wallet": wallet[:12] + "...",
            "pseudonym": trades_list[-1].get("pseudonym", "Anonymous"),
            "trade_count": len(trades_list),
            "total_volume": data["total_volume"],
            "avg_trade": avg_trade,
            "tier": tier,
        })
    profiles.sort(key=lambda x: x["total_volume"], reverse=True)

    # Whale Brief (market-level)
    market_activity = defaultdict(lambda: {"buys": 0, "sells": 0, "whale_buys": 0, "whale_sells": 0, "volume": 0, "trades": 0})
    for t in all_trades:
        mkt = (t.get("title") or "Unknown")[:55]
        side = t.get("side", "BUY")
        usd = float(t.get("size", 0)) * float(t.get("price", 0))
        market_activity[mkt]["volume"] += usd
        market_activity[mkt]["trades"] += 1
        if side == "BUY":
            market_activity[mkt]["buys"] += 1
            if usd >= WHALE_THRESHOLD_USD:
                market_activity[mkt]["whale_buys"] += 1
        else:
            market_activity[mkt]["sells"] += 1
            if usd >= WHALE_THRESHOLD_USD:
                market_activity[mkt]["whale_sells"] += 1

    brief = []
    for mkt, act in market_activity.items():
        score = 0
        signals = []
        if act["whale_buys"] >= 1:
            score += 40
            signals.append("Whale accumulation")
        if act["whale_sells"] >= 1:
            score += 30
            signals.append("Whale distribution")
        if act["buys"] > act["sells"] * 1.5:
            score += 15
            signals.append("Buy imbalance")
        if act["volume"] >= 20_000:
            score += 15
            signals.append("High volume")
        brief.append({
            "market": mkt,
            "score": min(score, 100),
            "signals": signals,
            "volume": act["volume"],
            "whale_buys": act["whale_buys"],
            "whale_sells": act["whale_sells"],
            "total_trades": act["trades"],
        })
    brief.sort(key=lambda x: x["score"], reverse=True)

    return whale_alerts, profiles, brief[:5]


def _csv_download_button(df: pd.DataFrame, filename: str, label: str = "📥 Download CSV"):
    """Render a Streamlit download button for a DataFrame."""
    if df.empty:
        return
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label=label, data=csv, file_name=filename, mime="text/csv")


def _parse_price_ladder(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Detect price-ladder events (Polymarket HIGH/LOW or Kalshi below/above) and return parsed frame."""
    records = []
    for _, row in df.iterrows():
        q = row["question"]
        # 1. Polymarket: "(HIGH) $150" or "(LOW) $20"
        m = re.search(r'\((HIGH|LOW)\)\s*\$([\d,]+)', q, re.IGNORECASE)
        if m:
            records.append({
                "question": q,
                "yes_price": row["yes_price"],
                "volume": row["volume"],
                "direction": m.group(1).upper(),
                "strike": int(m.group(2).replace(",", "")),
            })
            continue
        # 2. Kalshi: "below $75000.00" or "above $6845.5"
        m = re.search(r'(below|above)\s*\$([\d,.]+)', q, re.IGNORECASE)
        if m:
            direction = "LOW" if m.group(1).lower() == "below" else "HIGH"
            try:
                strike_val = float(m.group(2).replace(",", ""))
                records.append({
                    "question": q,
                    "yes_price": row["yes_price"],
                    "volume": row["volume"],
                    "direction": direction,
                    "strike": strike_val,
                })
            except ValueError:
                pass
    if len(records) < 3:
        return None
    return pd.DataFrame(records).sort_values("strike")


def _render_price_ladder_chart(ladder_df: pd.DataFrame):
    """Render a line chart for price-ladder probabilities."""
    fig = go.Figure()
    for direction, color in [("HIGH", "#ef4444"), ("LOW", "#10b981")]:
        sub = ladder_df[ladder_df["direction"] == direction]
        if not sub.empty:
            fig.add_trace(go.Scatter(
                x=sub["strike"],
                y=sub["yes_price"],
                mode="lines+markers",
                name=f"{direction} Hit",
                line=dict(color=color, width=3),
                marker=dict(size=10, color=color),
                hovertemplate="Strike: $%{x}<br>Yes: %{y:.1%}<extra></extra>",
            ))
    fig.update_layout(
        title=dict(text="Implied Probability by Strike Price", font_color="#f3f4f6", x=0.5),
        xaxis=dict(title="Strike Price ($)", color="#9ca3af", gridcolor="#1f2937"),
        yaxis=dict(title="Yes Probability", tickformat=".0%", color="#9ca3af", gridcolor="#1f2937", range=[-0.05, 1.05]),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9ca3af"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font_color="#f3f4f6"),
        height=420,
        margin=dict(t=80, b=60),
    )
    st.plotly_chart(fig, use_container_width=True)


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
        SELECT m.id, m.platform, m.question, m.slug, m.category, m.volume,
               m.outcome_prices, m.end_date,
               (SELECT spread FROM price_snapshots WHERE market_id = m.id ORDER BY snapshot_date DESC LIMIT 1) as spread,
               (SELECT best_bid FROM price_snapshots WHERE market_id = m.id ORDER BY snapshot_date DESC LIMIT 1) as best_bid,
               (SELECT best_ask FROM price_snapshots WHERE market_id = m.id ORDER BY snapshot_date DESC LIMIT 1) as best_ask
        FROM markets m
        ORDER BY m.volume DESC
    """)
    rows = cur.fetchall()
    cur.close()

    data = []
    for mid, platform, question, slug, category, volume, prices_json, end_date, spread, best_bid, best_ask in rows:
        try:
            if isinstance(prices_json, str):
                prices = json.loads(prices_json)
            else:
                prices = prices_json or []
            yes_price = float(prices[0]) if prices else 0
        except Exception:
            yes_price = 0
        data.append({
            "id": mid, "platform": platform, "question": question, "slug": slug or "",
            "category": category or "Other", "volume": float(volume or 0),
            "yes_price": yes_price, "end_date": end_date,
            "spread": float(spread or 0), "best_bid": float(best_bid or 0), "best_ask": float(best_ask or 0),
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
            if isinstance(prices_json, str):
                prices = json.loads(prices_json)
            else:
                prices = prices_json or []
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
col_logo, col_title = st.columns([0.12, 0.88], vertical_alignment="center")
with col_logo:
    st.markdown("""
        <style>
        /* ---------- Radar Scanner Logo ---------- */
        .radar-wrap {
            position: relative;
            width: 72px; height: 72px;
            display: flex; align-items: center; justify-content: center;
            margin: 0 auto;
        }

        /* Rotating scan beam */
        .radar-scan {
            position: absolute;
            inset: -10px;
            border-radius: 50%;
            background: conic-gradient(from 0deg, transparent 0deg, rgba(6,182,212,0.35) 45deg, rgba(139,92,246,0.15) 90deg, transparent 120deg);
            animation: radar-spin 2.2s linear infinite;
            pointer-events: none;
        }
        @keyframes radar-spin {
            from { transform: rotate(0deg); }
            to   { transform: rotate(360deg); }
        }

        /* Outer dashed ring (counter-rotate) */
        .radar-ring {
            position: absolute;
            inset: -6px;
            border-radius: 50%;
            border: 1.5px dashed rgba(6,182,212,0.35);
            animation: radar-spin-reverse 10s linear infinite;
            pointer-events: none;
        }
        @keyframes radar-spin-reverse {
            from { transform: rotate(360deg); }
            to   { transform: rotate(0deg); }
        }

        /* Inner pulse ring */
        .radar-pulse {
            position: absolute;
            inset: -2px;
            border-radius: 50%;
            border: 1px solid rgba(6,182,212,0.2);
            animation: radar-pulse 2.8s ease-in-out infinite;
            pointer-events: none;
        }
        @keyframes radar-pulse {
            0%   { transform: scale(1);   opacity: 0.6; }
            50%  { transform: scale(1.15); opacity: 0.2; }
            100% { transform: scale(1);   opacity: 0.6; }
        }

        /* Liquid-glass QS badge */
        .qs-liquid {
            width: 56px; height: 56px; border-radius: 14px;
            background: rgba(255,255,255,0.06);
            backdrop-filter: blur(14px) saturate(180%);
            -webkit-backdrop-filter: blur(14px) saturate(180%);
            border: 1px solid rgba(255,255,255,0.12);
            box-shadow: inset 0 1px 1px rgba(255,255,255,0.15), 0 8px 32px rgba(6,182,212,0.25);
            display: flex; align-items: center; justify-content: center;
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.5rem; font-weight: 800; color: #ffffff;
            letter-spacing: -0.04em;
            position: relative;
            z-index: 2;
            overflow: hidden;
        }
        /* Shimmer sweep inside the badge */
        .qs-liquid::before {
            content: '';
            position: absolute;
            top: -50%; left: -50%;
            width: 200%; height: 200%;
            background: linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.08) 50%, transparent 70%);
            animation: shimmer-sweep 4s ease-in-out infinite;
            pointer-events: none;
        }
        @keyframes shimmer-sweep {
            0%   { transform: translateX(-100%) rotate(0deg); }
            100% { transform: translateX(100%) rotate(0deg); }
        }
        </style>

        <div class="radar-wrap">
            <div class="radar-scan"></div>
            <div class="radar-ring"></div>
            <div class="radar-pulse"></div>
            <div class="qs-liquid">QS</div>
        </div>
    """, unsafe_allow_html=True)
with col_title:
    st.markdown("""
        <h1 style='margin:0; font-weight:800; background: linear-gradient(90deg, #06b6d4, #8b5cf6);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
            QS Flow Detector
        </h1>
        <p style='margin:0; color:#6b7280; font-size:1rem; font-weight:300;'>
            Prediction Market Intelligence Layer
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
# Breaking News Helpers
# ------------------------------------------------------------------
def _compute_heat_score(row):
    """Heat score = volume dominance + price extremity (closer to 0/100 = hotter) + spread activity."""
    vol = float(row.get("volume", 0))
    price = float(row.get("yes_price", 0.5))
    spread = float(row.get("spread", 0))
    vol_score = min((vol / 1_000_000) * 15, 50)
    extremity = (1 - abs(price - 0.5) * 2) * 35
    spread_score = min(spread * 200, 15)
    return vol_score + extremity + spread_score


def get_featured_events(df_markets: pd.DataFrame):
    """Auto-detect hottest event groups for Breaking News.

    Algorithm:
        1. Extract shared suffixes from Polymarket market questions
        2. Group markets by shared suffixes (>=3 markets per group)
        3. Sort by total volume, return top 3
        4. Fallback: return top 3 individual hot markets if no groups found
    """
    from collections import Counter, defaultdict

    poly = df_markets[df_markets["platform"] == "polymarket"].copy()
    if poly.empty or len(poly) < 3:
        return []

    poly["heat"] = poly.apply(_compute_heat_score, axis=1)

    # ---- Phase 1: Auto-detect event groups by shared question suffixes ----
    def _extract_suffixes(q: str):
        q = q.replace("Will ", "").replace("?", "").strip()
        words = q.split()
        out = []
        # Generate suffixes of 5-10 words
        for length in range(5, min(11, len(words) + 1)):
            for i in range(len(words) - length + 1):
                suffix = " ".join(words[i:i + length]).lower()
                # Skip generic date-only suffixes
                if any(suffix.endswith(x) for x in ["by 2026", "by 2025", "in 2026", "in 2025", "before 2026", "before 2025"]):
                    if len(suffix.split()) <= 6:
                        continue
                out.append(suffix)
        # Limit per question to avoid explosion
        return out[:40]

    suffix_counter = Counter()
    suffix_indices = defaultdict(list)

    for idx, q in enumerate(poly["question"].tolist()):
        for s in _extract_suffixes(q):
            suffix_counter[s] += 1
            suffix_indices[s].append(idx)

    event_groups = []
    used = set()

    for suffix, count in suffix_counter.most_common(40):
        if count < 3:
            continue
        indices = [i for i in suffix_indices[suffix] if i not in used]
        if len(indices) < 3:
            continue

        gdf = poly.iloc[indices]
        total_vol = float(gdf["volume"].sum())
        if total_vol < 5000:
            continue

        # Clean group name
        name = suffix.title()
        if len(name) > 50:
            name = name[:50] + "..."

        # Auto icon — check representative questions (not just suffix) for accuracy
        icon = "🔥"
        sample_qs = " ".join(gdf["question"].head(3).tolist()).lower()
        sl = suffix.lower()
        text = f"{sl} {sample_qs}"

        # Politics (high priority — check first)
        if any(k in text for k in ["trump", "biden", "election", "president", "impeach", "vote", "congress", "senate", "mayoral", "mayor", "governor", "candidate", "primary"]):
            icon = "🏛️"
        # Sports
        elif any(k in text for k in ["champions league", "world cup", "super bowl", "nba", "nfl", "football", "soccer", "top scorer", "goal scorer", "win the ucl", "champions"]):
            icon = "⚽"
        # Crypto
        elif any(k in text for k in ["bitcoin", "btc", "crypto", "ethereum", "eth"]):
            icon = "₿"
        # Geopolitics
        elif any(k in text for k in ["hormuz", "ukraine", "russia", "war", "ceasefire", "gaza", "israel", "iran", "china", "blockade", "strait"]):
            icon = "🌍"
        # Finance / Stocks
        elif any(k in text for k in ["nvidia", "tesla", "apple", "company", "market cap", "stock", "price", "spy", "spx", "s&p", "largest company"]):
            icon = "📈"
        # Entertainment
        elif any(k in text for k in ["jesus", "gta", "album", "movie", "oscar", "music", "song"]):
            icon = "🎬"
        # Commodities
        elif any(k in text for k in ["oil", "wti", "crude", "gas", "energy", "gold", "silver", "commodity"]):
            icon = "⛽"

        top = gdf.sort_values("volume", ascending=False).iloc[0]
        event_groups.append({
            "group": name,
            "icon": icon,
            "top_question": top["question"],
            "top_price": float(top["yes_price"]),
            "top_volume": float(top["volume"]),
            "total_volume": total_vol,
            "markets_count": len(gdf),
            "heat": gdf["heat"].max(),
            "markets": gdf.sort_values("volume", ascending=False),
        })
        used.update(indices)
        if len(event_groups) >= 6:
            break

    # Sort by total volume descending
    event_groups.sort(key=lambda x: x["total_volume"], reverse=True)

    # ---- Phase 1b: Prioritize tracked events so they always show ----
    priority_keywords = ["trump speak", "starmer", "prime minister"]
    priority = []
    regular = []
    for eg in event_groups:
        text = f"{eg['group']} {eg['top_question']}".lower()
        if any(kw in text for kw in priority_keywords):
            priority.append(eg)
        else:
            regular.append(eg)
    # Priority first, then top-volume regular events fill remaining slots
    event_groups = priority + regular

    # ---- Phase 2: Fallback — top 3 individual hot markets ----
    if not event_groups:
        top3 = poly.sort_values("heat", ascending=False).head(3)
        for _, row in top3.iterrows():
            q = row["question"]
            short = q.replace("Will ", "").replace("?", "")[:50]
            event_groups.append({
                "group": short + ("..." if len(q) > 50 else ""),
                "icon": "🔥",
                "top_question": q,
                "top_price": float(row["yes_price"]),
                "top_volume": float(row["volume"]),
                "total_volume": float(row["volume"]),
                "markets_count": 1,
                "heat": row["heat"],
                "markets": pd.DataFrame([row]),
            })

    return event_groups[:5]


# Compute featured events once (used by both home & detail page)
featured = get_featured_events(df_markets)

# ------------------------------------------------------------------
# Detail Page Router — renders standalone detail page when ?event=XXX
# ------------------------------------------------------------------
query_params = st.query_params
detail_event = query_params.get("event")

if detail_event and featured:
    selected = next((f for f in featured if f["group"] == detail_event), None)
    if selected:
        # Scroll to top
        st.markdown("""
        <script>
            window.scrollTo({top: 0, behavior: 'instant'});
        </script>
        """, unsafe_allow_html=True)

        st.markdown('<div class="detail-page">', unsafe_allow_html=True)

        # Header
        hc1, hc2 = st.columns([0.8, 0.2])
        with hc1:
            st.markdown(f"""
            <div class="detail-header">
                <div class="detail-title">
                    <span style="font-size:2rem;">{selected['icon']}</span>
                    <span>{selected['group']}</span>
                </div>
                <div class="detail-badge">🔴 LIVE BREAKING</div>
            </div>
            """, unsafe_allow_html=True)
        with hc2:
            st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
            if st.button("⬅️ Back", key="back_breaking", use_container_width=True):
                del st.query_params["event"]
                st.rerun()

        # Stat cards
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            st.markdown(f"""
            <div class="detail-stat-box">
                <div class="detail-stat-value">{selected['markets_count']}</div>
                <div class="detail-stat-label">Markets</div>
            </div>
            """, unsafe_allow_html=True)
        with sc2:
            vol_disp = f"${selected['total_volume']/1e6:.1f}M" if selected['total_volume'] >= 1e6 else f"${selected['total_volume']:,.0f}"
            st.markdown(f"""
            <div class="detail-stat-box">
                <div class="detail-stat-value">{vol_disp}</div>
                <div class="detail-stat-label">Total Volume</div>
            </div>
            """, unsafe_allow_html=True)
        with sc3:
            st.markdown(f"""
            <div class="detail-stat-box">
                <div class="detail-stat-value">{selected['heat']:.0f}</div>
                <div class="detail-stat-label">Heat Score</div>
            </div>
            """, unsafe_allow_html=True)
        with sc4:
            st.markdown(f"""
            <div class="detail-stat-box">
                <div class="detail-stat-value">{selected['top_price']:.0%}</div>
                <div class="detail-stat-label">Top Pick</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

        # --- Customer-friendly visualizations ---
        mkts = selected["markets"].sort_values("yes_price", ascending=False).reset_index(drop=True)

        # 1) DONUT CHART — Top 5 + Others
        st.subheader("Probability Share")
        top5 = mkts.head(5).copy()
        others_prob = mkts.iloc[5:]["yes_price"].sum() if len(mkts) > 5 else 0
        pie_labels = []
        pie_values = []
        for _, r in top5.iterrows():
            short = r["question"].replace("Will ", "").replace(" win the 2025–26 Champions League?", "").replace(" be the largest company in the world by market cap on May 31?", "").replace("Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by ", "").replace("?", "")[:18]
            pie_labels.append(short)
            pie_values.append(float(r["yes_price"]))
        if others_prob > 0:
            pie_labels.append("Others")
            pie_values.append(float(others_prob))

        fig_pie = go.Figure(go.Pie(
            labels=pie_labels,
            values=pie_values,
            hole=0.58,
            textinfo="label+percent",
            textposition="outside",
            textfont=dict(color="#e5e7eb", size=11),
            marker=dict(colors=["#ef4444", "#f59e0b", "#10b981", "#06b6d4", "#8b5cf6", "#4b5563"],
                        line=dict(color="rgba(0,0,0,0.3)", width=2)),
            hovertemplate="%{label}<br>Yes: %{percent}<extra></extra>",
            pull=[0.05, 0, 0, 0, 0, 0],
        ))
        fig_pie.update_layout(
            showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ca3af"),
            height=340,
            margin=dict(t=20, b=20, l=20, r=20),
            annotations=[dict(text=f"<b>Top {min(5,len(mkts))}</b>", x=0.5, y=0.5, font_size=16, font_color="#f3f4f6", showarrow=False)],
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        # 2) TOP 10 BAR CHART (simplified, not all 60)
        if len(mkts) > 5:
            st.subheader("Top 10 Contenders")
            top10 = mkts.head(10).sort_values("yes_price", ascending=True)
            fig_bar = go.Figure(go.Bar(
                x=top10["yes_price"],
                y=[q.replace("Will ", "").replace(" win the 2025–26 Champions League?", "").replace(" be the largest company in the world by market cap on May 31?", "").replace("Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by ", "").replace("?", "")[:30] for q in top10["question"]],
                orientation='h',
                marker=dict(
                    color=top10["yes_price"],
                    colorscale=[[0, "#ef4444"], [0.4, "#f59e0b"], [0.6, "#10b981"], [1, "#10b981"]],
                    showscale=False,
                ),
                text=[f"{p:.0%}" for p in top10["yes_price"]],
                textposition="outside",
                textfont=dict(color="#f3f4f6", size=11),
                hovertemplate="%{y}<br>Yes: %{x:.1%}<extra></extra>",
            ))
            fig_bar.update_layout(
                xaxis=dict(tickformat=".0%", color="#9ca3af", gridcolor="#1f2937", range=[0, 1.1]),
                yaxis=dict(color="#9ca3af", gridcolor="#1f2937"),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#9ca3af"),
                height=max(320, len(top10) * 36),
                margin=dict(l=200, r=60, t=20, b=30),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        # 3) CLEAN LEADERBOARD TABLE
        st.subheader("Full Leaderboard")
        lb = mkts[["question", "yes_price", "volume"]].copy()
        lb["Rank"] = range(1, len(lb) + 1)
        lb["Probability"] = lb["yes_price"].apply(lambda x: f"{x:.1%}")
        lb["Volume"] = lb["volume"].apply(lambda x: f"${x/1e6:.2f}M" if x >= 1e6 else f"${x:,.0f}")
        # Shorten question names
        lb["Name"] = lb["question"].apply(lambda q: q.replace("Will ", "").replace(" win the 2025–26 Champions League?", "").replace(" be the largest company in the world by market cap on May 31?", "").replace("Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by ", "").replace("?", "")[:40])
        st.dataframe(
            lb[["Rank", "Name", "Probability", "Volume"]],
            column_config={"Rank": st.column_config.NumberColumn("#", width="small")},
            hide_index=True,
            use_container_width=True,
        )

        st.markdown('</div>', unsafe_allow_html=True)

    if conn:
        conn.close()
    st.stop()

# ------------------------------------------------------------------
# Breaking News — Polymarket Heat Top 3 (Animated)
# ------------------------------------------------------------------
st.markdown("""
<style>
    @keyframes ticker {
        0% { transform: translateX(100%); }
        100% { transform: translateX(-100%); }
    }
    @keyframes pulse-red {
        0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.5); }
        50% { box-shadow: 0 0 25px rgba(239, 68, 68, 0.3); }
        100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.5); }
    }
    @keyframes blink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }
    .breaking-ticker-wrap {
        width: 100%;
        overflow: hidden;
        background: linear-gradient(90deg, #1a0a0a, #2d1515, #1a0a0a);
        border: 1px solid #ef4444;
        border-radius: 8px;
        margin-bottom: 16px;
        padding: 8px 0;
        position: relative;
    }
    .breaking-ticker {
        display: inline-block;
        white-space: nowrap;
        animation: ticker 45s linear infinite;
        color: #fca5a5;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.9rem;
        font-weight: 600;
        padding-left: 100%;
    }
    .breaking-card {
        border: 1px solid #ef4444;
        border-radius: 12px;
        background: linear-gradient(135deg, rgba(239,68,68,0.08), rgba(17,24,39,0.95));
        padding: 18px;
        position: relative;
        overflow: hidden;
        transition: all 0.3s ease;
    }
    .breaking-card::before {
        content: '';
        position: absolute;
        top: 0; left: -100%; width: 50%; height: 100%;
        background: linear-gradient(90deg, transparent, rgba(239,68,68,0.15), transparent);
        animation: shimmer 3s infinite;
    }
    @keyframes shimmer {
        0% { left: -100%; }
        100% { left: 200%; }
    }
    .live-dot {
        display: inline-block;
        width: 8px; height: 8px;
        background: #ef4444;
        border-radius: 50%;
        margin-right: 6px;
        animation: blink 1.2s infinite;
        box-shadow: 0 0 8px #ef4444;
    }
    .breaking-label {
        display: inline-flex;
        align-items: center;
        background: #ef4444;
        color: white;
        font-size: 0.65rem;
        font-weight: 800;
        padding: 3px 10px;
        border-radius: 4px;
        letter-spacing: 0.1em;
        margin-bottom: 10px;
        text-transform: uppercase;
    }
    .breaking-rank {
        font-size: 2.2rem;
        font-weight: 900;
        color: rgba(239,68,68,0.9);
        line-height: 1;
        margin-right: 12px;
        font-family: 'JetBrains Mono', monospace;
        text-shadow: 0 0 15px rgba(239,68,68,0.4);
    }
    .breaking-title {
        font-size: 1rem;
        font-weight: 700;
        color: #f3f4f6;
        line-height: 1.3;
    }
    .breaking-meta {
        font-size: 0.78rem;
        color: #9ca3af;
        margin-top: 5px;
    }
    .breaking-score-box {
        text-align: right;
    }
    .breaking-score-val {
        font-size: 1.6rem;
        font-weight: 800;
        color: #ef4444;
        font-family: 'JetBrains Mono', monospace;
        text-shadow: 0 0 12px rgba(239,68,68,0.35);
    }
    .breaking-price-val {
        font-size: 1.4rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
    }
    /* --- Detail Overlay (Glassmorphism Page) --- */
    .detail-page {
        background: linear-gradient(135deg, rgba(10,14,26,0.97), rgba(26,14,18,0.97));
        border: 1px solid rgba(239,68,68,0.25);
        border-radius: 16px;
        padding: 32px;
        margin: 0 0 40px 0;
        animation: slideUp 0.4s ease-out;
    }
    @keyframes slideUp {
        from { opacity: 0; transform: translateY(30px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .detail-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 24px;
        padding-bottom: 16px;
        border-bottom: 1px solid rgba(239,68,68,0.2);
    }
    .detail-title {
        font-size: 1.5rem;
        font-weight: 800;
        color: #f3f4f6;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .detail-badge {
        background: rgba(239,68,68,0.15);
        border: 1px solid rgba(239,68,68,0.4);
        color: #fca5a5;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 4px 12px;
        border-radius: 20px;
    }
    .detail-stat-box {
        background: rgba(17,24,39,0.5);
        border: 1px solid rgba(55,65,81,0.4);
        border-radius: 10px;
        padding: 16px;
        text-align: center;
    }
    .detail-stat-value {
        font-size: 1.5rem;
        font-weight: 800;
        color: #ef4444;
        font-family: 'JetBrains Mono', monospace;
    }
    .detail-stat-label {
        font-size: 0.75rem;
        color: #9ca3af;
        margin-top: 4px;
    }
    /* Glassmorphism buttons for Breaking News */
    [data-testid="stButton"] > button {
        background: rgba(239, 68, 68, 0.06) !important;
        border: 1px solid rgba(239, 68, 68, 0.35) !important;
        color: #fca5a5 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        backdrop-filter: blur(8px) !important;
        -webkit-backdrop-filter: blur(8px) !important;
        transition: all 0.25s ease !important;
        box-shadow: none !important;
    }
    [data-testid="stButton"] > button:hover {
        background: rgba(239, 68, 68, 0.18) !important;
        border-color: #ef4444 !important;
        color: #ffffff !important;
        box-shadow: 0 0 18px rgba(239, 68, 68, 0.35) !important;
        transform: translateY(-1px);
    }
    [data-testid="stButton"] > button:active {
        transform: translateY(0px);
        background: rgba(239, 68, 68, 0.25) !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h3 style='color:#ef4444; font-weight:800; margin-bottom:0.3rem; display:flex; align-items:center;'><span class='live-dot'></span>🔴 BREAKING NEWS</h3>", unsafe_allow_html=True)

# --- Marquee Ticker (uses pre-computed featured) ---
if featured:
    ticker_text = "    ·    ".join(
        [f"{f['icon']} {f['group'][:35]}... (Heat {f['heat']:.0f})" for f in featured[:3]]
    )
    st.markdown(f"""
    <div class="breaking-ticker-wrap">
        <div class="breaking-ticker">🔴 LIVE  {ticker_text}  ·  🔴 LIVE  {ticker_text}</div>
    </div>
    """, unsafe_allow_html=True)

    # --- Featured Cards with Buttons ---
    cols = st.columns(min(3, len(featured)))
    for col, f in zip(cols, featured[:3]):
        price = f["top_price"]
        price_color = "#10b981" if price > 0.6 else "#f59e0b" if price > 0.4 else "#ef4444"
        vol_str = f"${f['total_volume']/1e6:.2f}M" if f['total_volume'] >= 1e6 else f"${f['total_volume']:,.0f}"
        with col:
            st.markdown(f"""
            <div class="breaking-card">
                <div class="breaking-label"><span class="live-dot"></span>Breaking</div>
                <div style="display:flex; align-items:flex-start; margin-bottom:10px;">
                    <div style="font-size:2rem; margin-right:10px;">{f['icon']}</div>
                    <div>
                        <div class="breaking-title">{f['group'][:45]}</div>
                        <div class="breaking-meta">{f['markets_count']} markets · Total Vol {vol_str}</div>
                    </div>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:14px; border-top:1px solid rgba(239,68,68,0.15); padding-top:10px;">
                    <div>
                        <div style="font-size:0.7rem; color:#6b7280; margin-bottom:2px;">Top Pick Price</div>
                        <div class="breaking-price-val" style="color:{price_color};">{price:.0%}</div>
                    </div>
                    <div class="breaking-score-box">
                        <div style="font-size:0.7rem; color:#6b7280; margin-bottom:2px;">Heat Score</div>
                        <div class="breaking-score-val">{f['heat']:.0f}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"📊 View Details", key=f"btn_{f['group']}", use_container_width=True):
                st.query_params["event"] = f["group"]
                st.rerun()
else:
    st.info("No Polymarket data to generate Breaking News.")

st.divider()

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
tab_poly, tab_kalshi, tab_arb, tab_signals, tab_whale, tab_insights = st.tabs([
    "🟣  Polymarket", "🔵  Kalshi", "⚡  Arbitrage", "🚨  Signals", "🐋  Whale Radar", "📈  Insights"
])

# ---------- Polymarket ----------
with tab_poly:
    st.markdown("<h2 style='color:#8b5cf6;'>Polymarket</h2>", unsafe_allow_html=True)
    st.caption("Crypto-native. Higher volume. Global liquidity.")

    poly = df_markets[df_markets["platform"] == "polymarket"].sort_values("volume", ascending=False)
    search_poly = st.text_input("🔍 Search Polymarket markets", "", key="search_poly", placeholder="e.g. SPY, WTI, Trump...")
    if search_poly:
        mask = poly["question"].str.contains(search_poly, case=False, na=False) | poly["slug"].str.contains(search_poly, case=False, na=False)
        poly = poly[mask]
    if not poly.empty:
        # ----- Horizontal bar chart: Yes Price overview -----
        bar = poly.sort_values("yes_price", ascending=True).tail(15)
        fig_bar = go.Figure(go.Bar(
            x=bar["yes_price"],
            y=bar["question"].str[:55],
            orientation='h',
            marker=dict(
                color=bar["yes_price"],
                colorscale=[[0, "#ef4444"], [0.4, "#f59e0b"], [0.6, "#10b981"], [1, "#10b981"]],
                showscale=False,
                line=dict(color="rgba(255,255,255,0.1)", width=1),
            ),
            text=[f"{p:.0%}" for p in bar["yes_price"]],
            textposition="outside",
            textfont=dict(color="#f3f4f6", size=12),
            hovertemplate="%{y}<br>Yes: %{x:.1%}<extra></extra>",
        ))
        fig_bar.update_layout(
            title=dict(text="Yes Probability (Top 15)", font_color="#f3f4f6", x=0.5, font_size=14),
            xaxis=dict(tickformat=".0%", color="#9ca3af", gridcolor="#1f2937", range=[0, 1.15]),
            yaxis=dict(color="#9ca3af", gridcolor="#1f2937", autorange="reversed"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ca3af"),
            height=max(300, len(bar) * 35),
            margin=dict(l=220, r=80, t=50, b=40),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # ----- Price-ladder line chart (e.g. WTI) -----
        ladder = _parse_price_ladder(poly)
        if ladder is not None:
            st.divider()
            _render_price_ladder_chart(ladder)

        st.divider()

        # Fix categories using NLP inference so Champions League shows Sports not Financials
        poly["category"] = poly.apply(lambda r: infer_category(r["question"], r["category"]), axis=1)

        # -------- Ultra-compact premium cards --------
        show_all = st.toggle("Show all markets", value=False, key="poly_show_all")
        display_limit = len(poly) if show_all else 8
        display_df = poly.head(display_limit)

        cards = []
        for _, row in display_df.iterrows():
            price = row["yes_price"]
            price_color = "#10b981" if price > 0.6 else "#f59e0b" if price > 0.4 else "#ef4444"
            vol = f"${row['volume']/1e6:.2f}M" if row['volume'] >= 1e6 else f"${row['volume']:,.0f}"
            cat = row["category"]
            theme = CATEGORY_THEME.get(cat, {"icon": "📌", "color": "#9ca3af"})
            q = row["question"]
            q_disp = q[:50] + ("..." if len(q) > 50 else "")
            cards.append(f"""
                <div style="background: linear-gradient(90deg, rgba(139,92,246,0.06), rgba(17,24,39,0.4));
                    border: 1px solid rgba(139,92,246,0.12);
                    border-radius: 8px;
                    padding: 8px 12px;
                    margin-bottom: 6px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: 12px;">
                    <div style="flex:1; min-width:0;">
                        <div style="font-size:0.85rem; font-weight:600; color:#f3f4f6; line-height:1.2;">{q_disp}</div>
                        <div style="margin-top:3px;">
                            <span style="display:inline-block; font-size:0.62rem; font-weight:600;
                                color:{theme['color']}; background:{theme['color']}15;
                                padding: 1px 7px; border-radius: 20px; line-height:1.3;">
                                {theme['icon']} {cat}
                            </span>
                        </div>
                    </div>
                    <div style="text-align:right; white-space:nowrap;">
                        <div style="font-size:1rem; font-weight:700; color:{price_color}; font-family:'JetBrains Mono',monospace; line-height:1;">{price:.0%}</div>
                        <div style="font-size:0.68rem; color:#6b7280; margin-top:2px;">{vol}</div>
                    </div>
                </div>
            """)

        st.markdown("".join(cards), unsafe_allow_html=True)

        if not show_all and len(poly) > 10:
            st.caption(f"Showing top 10 of {len(poly)} markets — toggle above to expand")

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
        st.divider()
        _csv_download_button(poly[["question", "yes_price", "volume", "category"]].copy(), "polymarket_data.csv")
    else:
        st.info("No Polymarket data today.")


# ---------- Kalshi ----------
with tab_kalshi:
    st.markdown("<h2 style='color:#06b6d4;'>Kalshi</h2>", unsafe_allow_html=True)
    st.caption("Regulated US exchange. Politics & economics focus.")

    kal = df_markets[df_markets["platform"] == "kalshi"].sort_values("volume", ascending=False)
    search_kal = st.text_input("🔍 Search Kalshi markets", "", key="search_kal", placeholder="e.g. Fed, Trump, GDP...")
    if search_kal:
        mask = kal["question"].str.contains(search_kal, case=False, na=False) | kal["slug"].str.contains(search_kal, case=False, na=False)
        kal = kal[mask]
    if not kal.empty:
        # ----- Detect time-series events (e.g. SpaceX IPO monthly markets) -----
        def _extract_date_from_slug(slug: str) -> Optional[str]:
            """Extract YYMMM pattern from Kalshi tickers like kxipospacex-26jun01"""
            m = re.search(r'-([0-9]{2})([a-z]{3})([0-9]{2})', slug.lower())
            if m:
                yy, mon, dd = m.groups()
                return f"20{yy}-{mon.upper()}-{dd}"
            return None

        kal['event_group'] = kal['question'].str.replace(r'\s*\([^)]+\)\s*$', '', regex=True)
        grouped = kal.groupby('event_group')

        for event_name, group in grouped:
            if len(group) > 1:
                # Time-series event detected
                time_data = []
                for _, r in group.iterrows():
                    d = _extract_date_from_slug(r['slug'])
                    if d:
                        time_data.append({
                            'date': d,
                            'label': r['question'].split('(')[-1].replace(')', '') if '(' in r['question'] else r['slug'],
                            'yes_price': r['yes_price'],
                            'volume': r['volume'],
                        })
                if len(time_data) >= 3:
                    time_df = pd.DataFrame(time_data).sort_values('date')
                    fig_line = go.Figure()
                    fig_line.add_trace(go.Scatter(
                        x=time_df['label'],
                        y=time_df['yes_price'],
                        mode='lines+markers',
                        name='Yes Probability',
                        line=dict(color='#06b6d4', width=3),
                        marker=dict(size=10, color=time_df['yes_price'],
                                    colorscale=[[0, '#ef4444'], [0.4, '#f59e0b'], [0.6, '#10b981'], [1, '#10b981']],
                                    showscale=False, line=dict(color='rgba(255,255,255,0.2)', width=1)),
                        hovertemplate='%{x}<br>Yes: %{y:.1%}<br>Vol: $%{customdata:,.0f}<extra></extra>',
                        customdata=time_df['volume'],
                    ))
                    fig_line.update_layout(
                        title=dict(text=f"{event_name[:50]} — Probability Timeline", font_color='#f3f4f6', x=0.5, font_size=14),
                        xaxis=dict(title='', color='#9ca3af', gridcolor='#1f2937'),
                        yaxis=dict(title='Yes Probability', tickformat='.0%', color='#9ca3af', gridcolor='#1f2937', range=[-0.05, 1.05]),
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        font=dict(color='#9ca3af'),
                        height=380,
                        margin=dict(t=60, b=60),
                    )
                    st.plotly_chart(fig_line, use_container_width=True)

        # ----- Price-ladder line chart for Kalshi (e.g. BTC Minimum) -----
        kal_ladder = _parse_price_ladder(kal)
        if kal_ladder is not None:
            st.divider()
            fig_lad = go.Figure()
            for direction, color in [("HIGH", "#ef4444"), ("LOW", "#10b981")]:
                sub = kal_ladder[kal_ladder["direction"] == direction]
                if not sub.empty:
                    fig_lad.add_trace(go.Scatter(
                        x=sub["strike"],
                        y=sub["yes_price"],
                        mode="lines+markers",
                        name=f"{direction} Hit",
                        line=dict(color=color, width=3),
                        marker=dict(size=10, color=color),
                        hovertemplate="Strike: $%{x:,.0f}<br>Yes: %{y:.1%}<extra></extra>",
                    ))
            fig_lad.update_layout(
                title=dict(text="Implied Probability by Strike Price", font_color="#f3f4f6", x=0.5),
                xaxis=dict(title="Strike Price ($)", color="#9ca3af", gridcolor="#1f2937", tickformat=",.0f"),
                yaxis=dict(title="Yes Probability", tickformat=".0%", color="#9ca3af", gridcolor="#1f2937", range=[-0.05, 1.05]),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#9ca3af"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font_color="#f3f4f6"),
                height=420,
                margin=dict(t=80, b=60),
            )
            st.plotly_chart(fig_lad, use_container_width=True)

        # ----- Horizontal bar chart for Kalshi -----
        bar = kal.sort_values('yes_price', ascending=True).tail(15)
        fig_bar = go.Figure(go.Bar(
            x=bar['yes_price'],
            y=bar['question'].str[:55],
            orientation='h',
            marker=dict(
                color=bar['yes_price'],
                colorscale=[[0, '#ef4444'], [0.4, '#f59e0b'], [0.6, '#10b981'], [1, '#10b981']],
                showscale=False,
                line=dict(color='rgba(255,255,255,0.1)', width=1),
            ),
            text=[f'{p:.0%}' for p in bar['yes_price']],
            textposition='outside',
            textfont=dict(color='#f3f4f6', size=12),
            hovertemplate='%{y}<br>Yes: %{x:.1%}<extra></extra>',
        ))
        fig_bar.update_layout(
            title=dict(text='Kalshi Yes Probability', font_color='#f3f4f6', x=0.5, font_size=14),
            xaxis=dict(tickformat='.0%', color='#9ca3af', gridcolor='#1f2937', range=[0, 1.15]),
            yaxis=dict(color='#9ca3af', gridcolor='#1f2937', autorange='reversed'),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#9ca3af'),
            height=max(300, len(bar) * 35),
            margin=dict(l=220, r=80, t=50, b=40),
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        st.divider()

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
        st.divider()
        _csv_download_button(kal[["question", "yes_price", "volume", "category"]].copy(), "kalshi_data.csv")
    else:
        st.info("No Kalshi data today.")


# ---------- Arbitrage ----------
with tab_arb:
    st.markdown("<h2 style='color:#f59e0b;'>Cross-Market Arbitrage</h2>", unsafe_allow_html=True)
    st.caption("Price divergence signals between Polymarket and Kalshi.")

    if not df_arb.empty:
        # ----- Side-by-side comparison bar chart -----
        arb_sorted = df_arb.sort_values("spread", ascending=False)
        fig_arb = go.Figure()
        fig_arb.add_trace(go.Bar(
            y=arb_sorted["event_name"].str[:45],
            x=arb_sorted["poly_price"],
            name="Polymarket",
            orientation='h',
            marker=dict(color='#8b5cf6', line=dict(color='rgba(255,255,255,0.1)', width=1)),
            text=[f"{p:.0%}" for p in arb_sorted["poly_price"]],
            textposition="inside",
            textfont=dict(color="white", size=11),
            hovertemplate="%{y}<br>Polymarket: %{x:.1%}<extra></extra>",
        ))
        fig_arb.add_trace(go.Bar(
            y=arb_sorted["event_name"].str[:45],
            x=-arb_sorted["kalshi_price"],
            name="Kalshi",
            orientation='h',
            marker=dict(color='#06b6d4', line=dict(color='rgba(255,255,255,0.1)', width=1)),
            text=[f"{p:.0%}" for p in arb_sorted["kalshi_price"]],
            textposition="inside",
            textfont=dict(color="white", size=11),
            hovertemplate="%{y}<br>Kalshi: %{x:.1%}<extra></extra>",
        ))
        fig_arb.update_layout(
            title=dict(text="Cross-Platform Price Divergence", font_color="#f3f4f6", x=0.5, font_size=16),
            barmode="overlay",
            xaxis=dict(
                title="", color="#9ca3af", gridcolor="#1f2937",
                tickvals=[-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1],
                ticktext=["100%", "75%", "50%", "25%", "0%", "25%", "50%", "75%", "100%"],
                range=[-1.05, 1.05],
            ),
            yaxis=dict(title="", color="#9ca3af", gridcolor="#1f2937", autorange="reversed"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ca3af"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font_color="#f3f4f6"),
            height=max(350, len(arb_sorted) * 50),
            margin=dict(l=220, r=40, t=80, b=40),
        )
        st.plotly_chart(fig_arb, use_container_width=True)

        st.divider()

        # ----- Detail cards -----
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
        st.divider()
        _csv_download_button(arb_sorted[["event_name", "poly_price", "kalshi_price", "spread"]].copy(), "arbitrage_opportunities.csv")
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
    st.caption(f"QS Flow Detector v1.0  |  Data: {date.today()}  |  QuantSignals Research")


# ---------- Signals / Anomalies ----------
with tab_signals:
    st.markdown("<h2 style='color:#f59e0b;'>Anomaly Signals</h2>", unsafe_allow_html=True)
    st.caption("Real-time anomaly detection based on spread, volume & pricing.")

    def _compute_signal_score(row):
        score = 0
        reasons = []
        price = row.get("yes_price", 0.5)
        spread = row.get("spread", 0)
        vol = row.get("volume", 0)

        # 1. High spread (liquidity risk)
        if spread > 0.05:
            score += 30
            reasons.append("High spread")
        elif spread > 0.02:
            score += 15
            reasons.append("Wide spread")

        # 2. Extreme pricing
        if price > 0.95 or price < 0.05:
            score += 25
            reasons.append("Extreme pricing")
        elif price > 0.90 or price < 0.10:
            score += 15
            reasons.append("Near-certain outcome")

        # 3. High volume activity
        if vol >= 2_000_000:
            score += 20
            reasons.append("Very high volume")
        elif vol >= 500_000:
            score += 10
            reasons.append("High volume")

        # 4. Large bid-ask gap relative to price
        if price > 0 and spread / max(price, 0.01) > 0.5:
            score += 15
            reasons.append("Spread/price ratio high")

        return min(score, 100), reasons

    if not df_markets.empty:
        sig_data = []
        for _, row in df_markets.iterrows():
            score, reasons = _compute_signal_score(row)
            sig_data.append({
                "id": row["id"], "platform": row["platform"],
                "question": row["question"], "category": row.get("category", "Other"),
                "yes_price": row.get("yes_price", 0),
                "volume": row.get("volume", 0),
                "spread": row.get("spread", 0),
                "score": score, "reasons": reasons,
            })
        df_sig = pd.DataFrame(sig_data).sort_values("score", ascending=False)

        # KPI row
        k1, k2, k3 = st.columns(3)
        with k1:
            high_risk = len(df_sig[df_sig["score"] >= 60])
            st.metric("🔴 High Risk", high_risk)
        with k2:
            med_risk = len(df_sig[(df_sig["score"] >= 30) & (df_sig["score"] < 60)])
            st.metric("🟡 Medium Risk", med_risk)
        with k3:
            low_risk = len(df_sig[df_sig["score"] < 30])
            st.metric("🟢 Normal", low_risk)

        st.divider()

        # Signal cards
        top_signals = df_sig[df_sig["score"] > 0].head(15)
        if not top_signals.empty:
            for _, s in top_signals.iterrows():
                score = s["score"]
                if score >= 60:
                    border_color = "#ef4444"
                    bg_color = "rgba(239,68,68,0.08)"
                    emoji = "🔴"
                elif score >= 30:
                    border_color = "#f59e0b"
                    bg_color = "rgba(245,158,11,0.08)"
                    emoji = "🟡"
                else:
                    border_color = "#10b981"
                    bg_color = "rgba(16,185,129,0.08)"
                    emoji = "🟢"

                price = s["yes_price"]
                price_color = "#10b981" if price > 0.6 else "#f59e0b" if price > 0.4 else "#ef4444"
                vol_str = f"${s['volume']/1e6:.2f}M" if s['volume'] >= 1e6 else f"${s['volume']:,.0f}"
                reasons_html = " ".join([f"<span style='background:{border_color}22; color:{border_color}; padding:2px 8px; border-radius:4px; font-size:0.75rem; margin-right:4px;'>{r}</span>" for r in s["reasons"]])

                st.markdown(f"""
                <div style='background: linear-gradient(90deg, {bg_color}, transparent);
                    border-left: 3px solid {border_color}; padding: 16px 20px; border-radius: 8px;
                    margin-bottom: 12px;'>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <div style='flex:1;'>
                            <div style='font-size:1.05rem; font-weight:600; color:#f3f4f6; margin-bottom:6px;'>
                                {emoji} {s['question'][:65]}
                            </div>
                            <div style='margin-bottom:4px;'>{get_cat_badge(s['category'])}</div>
                            <div style='margin-top:6px;'>{reasons_html}</div>
                        </div>
                        <div style='text-align:right; margin-left:24px; min-width:80px;'>
                            <div style='font-size:1.5rem; font-weight:700; color:{price_color}; font-family:"JetBrains Mono",monospace;'>
                                {price:.0%}
                            </div>
                            <div style='font-size:0.7rem; color:#6b7280;'>Yes</div>
                        </div>
                        <div style='text-align:right; margin-left:24px; min-width:80px;'>
                            <div style='font-size:1.2rem; font-weight:700; color:#f3f4f6; font-family:"JetBrains Mono",monospace;'>
                                {score}
                            </div>
                            <div style='font-size:0.7rem; color:#6b7280;'>Score</div>
                        </div>
                        <div style='text-align:right; margin-left:24px; min-width:100px;'>
                            <div style='font-size:0.95rem; font-weight:600; color:#f3f4f6;'>{vol_str}</div>
                            <div style='font-size:0.7rem; color:#6b7280;'>Vol</div>
                        </div>
                    </div>
                    <div style='margin-top:8px; font-size:0.8rem; color:#6b7280;'>
                        Spread: {s['spread']:.2%} | Best Bid: {s.get('best_bid', 0):.3f} | Best Ask: {s.get('best_ask', 0):.3f}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            st.divider()
            _csv_download_button(top_signals[["question", "yes_price", "volume", "spread", "score"]].copy(), "anomaly_signals.csv")
        else:
            st.info("No anomalies detected. All markets appear normal.")

        # Volume vs Spread scatter
        st.divider()
        st.subheader("Volume vs Spread Landscape")
        fig_scatter = px.scatter(
            df_sig, x="spread", y="volume", color="score",
            size="volume", hover_name="question",
            color_continuous_scale=[[0, "#10b981"], [0.3, "#f59e0b"], [1, "#ef4444"]],
            height=420,
        )
        fig_scatter.update_traces(marker=dict(opacity=0.8, line=dict(color="rgba(255,255,255,0.2)", width=1)))
        fig_scatter.update_layout(
            xaxis=dict(title="Spread (Ask - Bid)", tickformat=".0%", color="#9ca3af", gridcolor="#1f2937"),
            yaxis=dict(title="Volume ($)", color="#9ca3af", gridcolor="#1f2937"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ca3af"),
            coloraxis_colorbar=dict(title=dict(text="Signal", font=dict(color="#f3f4f6")), tickfont=dict(color="#9ca3af")),
            margin=dict(t=40, b=60),
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        # Cross-platform divergence (placeholder if no kalshi data)
        st.divider()
        st.subheader("Cross-Platform Divergence")
        has_both = (df_markets["platform"] == "polymarket").any() and (df_markets["platform"] == "kalshi").any()
        if has_both:
            st.info("Divergence analysis requires matching events on both platforms. Auto-matching coming soon.")
        else:
            st.info("Add Kalshi markets to see cross-platform divergence signals. Currently only Polymarket data loaded.")
    else:
        st.info("No market data available for signal generation.")


# ---------- Whale Radar ----------
with tab_whale:
    st.markdown("<h2 style='color:#ef4444;'>🐋 Whale Radar</h2>", unsafe_allow_html=True)
    st.caption("Live CLOB trade-stream analysis from Polymarket data-api.")

    # --- Fetch live trades for top Polymarket markets ---
    pm_df = get_polymarket_markets(conn)
    all_trades = []
    fetched_markets = 0

    if not pm_df.empty:
        # --- Smart market selection ---
        priority_keywords = ["btc", "bitcoin", "spy", "spx", "s&p", "wti", "crude", "oil"]
        pm_df["lower_q"] = pm_df["question"].str.lower()
        pm_df["lower_s"] = pm_df["slug"].fillna("").str.lower()

        def _is_priority(row):
            text = f"{row['lower_q']} {row['lower_s']}"
            return any(kw in text for kw in priority_keywords)

        pm_df["is_priority"] = pm_df.apply(_is_priority, axis=1)
        priority_df = pm_df[pm_df["is_priority"]].drop_duplicates(subset=["condition_id"])
        others_df = pm_df[~pm_df["is_priority"]].head(3)
        top_markets = pd.concat([priority_df, others_df]).drop_duplicates(subset=["condition_id"]).head(8)

        st.caption(f"Scanning {len(top_markets)} markets: {len(priority_df)} priority + {len(others_df)} top volume")

        progress_bar = st.progress(0)
        status_text = st.empty()
        total = len(top_markets)
        for pos, (_, row) in enumerate(top_markets.iterrows(), start=1):
            cid = row.get("condition_id")
            if not cid or len(str(cid)) < 10:
                progress_bar.progress(min(int(pos / total * 100), 100))
                continue
            status_text.text(f"📡 Scanning {row['question'][:45]}...")
            trades = fetch_clob_trades(str(cid), limit=80)
            if trades:
                all_trades.extend(trades)
                fetched_markets += 1
            progress_bar.progress(min(int(pos / total * 100), 100))
        progress_bar.empty()
        status_text.empty()

    if not all_trades:
        st.info("""
        🐋 **Whale Radar is active** but no recent CLOB trade data was returned.

        Common reasons:
        - Markets are low-activity during this window
        - `data-api.polymarket.com` rate-limiting or downtime
        - No markets in the database have valid `condition_id`s

        Run `python fetcher.py` to populate the latest market metadata,
        or try again in a few minutes.
        """)
    else:
        whale_alerts, profiles, brief = analyze_whale_activity(all_trades)

        # --- KPI Row ---
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("🚨 Whale Alerts", len(whale_alerts))
        with k2:
            mega = len([a for a in whale_alerts if a["type"] == "MEGA WHALE"])
            st.metric("🔴 Mega Whales", mega)
        with k3:
            active_wallets = len([p for p in profiles if p["tier"] != "🐟 Retail"])
            st.metric("🐋 Active Whales", active_wallets)
        with k4:
            total_whale_vol = sum(a["usd"] for a in whale_alerts)
            st.metric("💰 Whale Volume", f"${total_whale_vol/1e6:.2f}M" if total_whale_vol >= 1e6 else f"${total_whale_vol:,.0f}")

        st.divider()

        # --- Whale Alerts ---
        left_col, right_col = st.columns([0.55, 0.45])
        with left_col:
            st.markdown("<h3 style='color:#ef4444;'>🚨 Live Whale Alerts</h3>", unsafe_allow_html=True)
            if whale_alerts:
                for alert in whale_alerts[:10]:
                    emoji = "🟢" if alert["side"] == "BUY" else "🔴"
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, {alert['color']}22, transparent);
                        border-left: 4px solid {alert['color']}; padding: 14px 18px; border-radius: 8px;
                        margin-bottom: 10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <div style="font-size:0.75rem; color:{alert['color']}; font-weight:700; margin-bottom:3px;">
                                    {alert['type']} ALERT
                                </div>
                                <div style="font-size:1rem; font-weight:600; color:#f3f4f6;">
                                    {emoji} {alert['side']} ${alert['usd']:,.0f} | {alert['market'][:50]}
                                </div>
                            </div>
                            <div style="text-align:right;">
                                <div style="font-size:0.75rem; color:#9ca3af;">Wallet</div>
                                <div style="font-size:0.85rem; color:#f3f4f6; font-family:'JetBrains Mono',monospace;">
                                    {alert['pseudonym']} ({alert['wallet']})
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No ≥$10K trades detected in current window. Markets may be quiet.")

        with right_col:
            st.markdown("<h3 style='color:#06b6d4;'>🐋 Smart Money Leaderboard</h3>", unsafe_allow_html=True)
            if profiles:
                top_profiles = profiles[:10]
                fig_w = go.Figure(go.Bar(
                    x=[p["avg_trade"] for p in top_profiles],
                    y=[f"{p['pseudonym']} ({p['wallet']})" for p in top_profiles],
                    orientation='h',
                    marker=dict(
                        color=[p["avg_trade"] for p in top_profiles],
                        colorscale=[[0, "#10b981"], [0.3, "#f59e0b"], [1, "#ef4444"]],
                        showscale=False,
                    ),
                    text=[f"${p['avg_trade']:,.0f}" for p in top_profiles],
                    textposition="outside",
                    textfont=dict(color="#f3f4f6", size=11),
                    hovertemplate="%{y}<br>Avg Trade: $%{x:,.0f}<br>Tier: %{customdata}<extra></extra>",
                    customdata=[p["tier"] for p in top_profiles],
                ))
                fig_w.update_layout(
                    title=dict(text="Avg Trade Size by Wallet", font_color="#f3f4f6", x=0.5, font_size=13),
                    xaxis=dict(title="Avg Trade ($)", color="#9ca3af", gridcolor="#1f2937"),
                    yaxis=dict(color="#9ca3af", gridcolor="#1f2937", autorange="reversed"),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#9ca3af"),
                    height=380,
                    margin=dict(l=180, r=60, t=50, b=40),
                )
                st.plotly_chart(fig_w, use_container_width=True)

                # Compact table
                tbl = pd.DataFrame(profiles[:8])
                tbl["total_volume"] = tbl["total_volume"].apply(lambda x: f"${x:,.0f}")
                tbl["avg_trade"] = tbl["avg_trade"].apply(lambda x: f"${x:,.0f}")
                st.dataframe(
                    tbl[["pseudonym", "trade_count", "avg_trade", "total_volume", "tier"]],
                    column_config={
                        "pseudonym": "Name", "trade_count": "Trades",
                        "avg_trade": "Avg Trade", "total_volume": "Volume", "tier": "Tier"
                    },
                    hide_index=True, use_container_width=True
                )
            else:
                st.info("No wallet activity to profile.")

        st.divider()

        # --- QS Whale Brief ---
        st.markdown("<h3 style='color:#f59e0b;'>📰 QS Whale Brief</h3>", unsafe_allow_html=True)
        st.caption(f"Top prediction-market signals by whale activity | {date.today()}")
        if brief:
            for i, sig in enumerate(brief, 1):
                border_color = "#ef4444" if sig["score"] >= 60 else "#f59e0b" if sig["score"] >= 30 else "#10b981"
                bg_color = f"{border_color}15"
                signals_html = " ".join([f'<span style="background:{border_color}33; color:{border_color}; padding:2px 8px; border-radius:4px; font-size:0.75rem; margin-right:4px;">{s}</span>' for s in sig["signals"]])
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, {bg_color}, transparent);
                    border-left: 4px solid {border_color}; padding: 18px; border-radius: 8px;
                    margin-bottom: 14px;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
                        <div>
                            <div style="font-size:1.1rem; font-weight:700; color:#f3f4f6; margin-bottom:3px;">
                                {i}. {sig['market']}
                            </div>
                            <div style="font-size:0.85rem; color:#9ca3af;">Score: {sig['score']}/100</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:1.4rem; font-weight:700; color:{border_color}; font-family:'JetBrains Mono',monospace;">
                                {sig['score']}
                            </div>
                        </div>
                    </div>
                    <div style="margin-bottom:8px;">{signals_html}</div>
                    <div style="display:flex; gap:20px; font-size:0.8rem; color:#9ca3af;">
                        <span>📊 {sig['total_trades']} trades</span>
                        <span>🟢 {sig['whale_buys']} whale buys</span>
                        <span>🔴 {sig['whale_sells']} whale sells</span>
                        <span>💰 ${sig['volume']:,.0f} volume</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No significant whale signals in current window.")

        st.divider()
        _csv_download_button(
            pd.DataFrame(whale_alerts)[["type", "side", "usd", "market", "wallet", "pseudonym"]].copy() if whale_alerts else pd.DataFrame(),
            "whale_alerts.csv",
            label="📥 Download Whale Alerts"
        )


if conn:
    conn.close()
