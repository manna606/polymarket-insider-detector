"""
Polymarket + Kalshi Daily Data Fetcher
============================================================
Collects daily snapshots of:
  - SPY, SPX, QQQ prediction markets
  - Top 5 trending/popular events
  - Prices, volumes, and recent trades

Stores results in PostgreSQL for alpha validation.

Usage:
    python fetcher.py

Environment:
    DATABASE_URL — PostgreSQL connection string
    KALSHI_API_KEY — (optional) for Kalshi trade data
============================================================
"""

import os
import re
import json
import time
from datetime import datetime, date
from typing import Optional, List, Dict

import requests

from local_db import get_db_conn, is_sqlite, sql_for_conn

# psycopg2 execute_values is used only for PostgreSQL bulk inserts
try:
    from psycopg2.extras import execute_values
except ImportError:
    execute_values = None

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
REQUEST_DELAY = 0.2

# Keywords for equity index markets
EQUITY_KEYWORDS = ["spy", "spx", "qqq", "s&p", "nasdaq", "sp500", "index"]


def upsert_market(conn, platform: str, data: dict) -> Optional[int]:
    """Insert or update a market row, return market_id."""
    if not conn:
        return None
    cur = conn.cursor()
    from datetime import datetime
    now = datetime.now()
    try:
        sql = sql_for_conn("""
            INSERT INTO markets (platform, external_id, slug, question, category,
                                 outcomes, outcome_prices, volume, liquidity, active, closed,
                                 end_date, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (platform, external_id)
            DO UPDATE SET
                question = EXCLUDED.question,
                category = EXCLUDED.category,
                outcomes = EXCLUDED.outcomes,
                outcome_prices = EXCLUDED.outcome_prices,
                volume = EXCLUDED.volume,
                liquidity = EXCLUDED.liquidity,
                active = EXCLUDED.active,
                closed = EXCLUDED.closed,
                end_date = EXCLUDED.end_date,
                updated_at = %s
            RETURNING id
        """, conn)
        cur.execute(
            sql,
            (
                platform,
                data["external_id"],
                data.get("slug"),
                data["question"],
                data.get("category"),
                json.dumps(data.get("outcomes", [])),
                json.dumps(data.get("outcome_prices", [])),
                data.get("volume", 0),
                data.get("liquidity", 0),
                data.get("active", True),
                data.get("closed", False),
                data.get("end_date"),
                now,
                now,
            ),
        )
        market_id = cur.fetchone()[0]
        conn.commit()
        return market_id
    except Exception as e:
        conn.rollback()
        print(f"[DB] upsert_market error: {e}")
        return None
    finally:
        cur.close()


def insert_snapshot(conn, market_id: int, snapshot: dict):
    if not conn:
        return
    cur = conn.cursor()
    try:
        sql = sql_for_conn("""
            INSERT INTO price_snapshots (market_id, snapshot_date, outcome_prices,
                                         volume, open_interest, spread, best_bid, best_ask)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (market_id, snapshot_date)
            DO UPDATE SET
                outcome_prices = EXCLUDED.outcome_prices,
                volume = EXCLUDED.volume,
                open_interest = EXCLUDED.open_interest,
                spread = EXCLUDED.spread,
                best_bid = EXCLUDED.best_bid,
                best_ask = EXCLUDED.best_ask
        """, conn)
        cur.execute(
            sql,
            (
                market_id,
                snapshot["date"],
                json.dumps(snapshot["outcome_prices"]),
                snapshot.get("volume", 0),
                snapshot.get("open_interest", 0),
                snapshot.get("spread", 0),
                snapshot.get("best_bid", 0),
                snapshot.get("best_ask", 0),
            ),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[DB] insert_snapshot error: {e}")
    finally:
        cur.close()


def insert_trades(conn, market_id: int, trades: List[dict]):
    if not conn or not trades:
        return
    cur = conn.cursor()
    try:
        vals = [
            (
                "polymarket",
                market_id,
                t.get("transactionHash"),
                t.get("proxyWallet", "").lower(),
                t.get("pseudonym") or t.get("name") or "anon",
                t.get("side"),
                t.get("outcome"),
                t.get("size", 0),
                t.get("price", 0),
                float(t.get("size", 0)) * float(t.get("price", 0)),
                datetime.fromtimestamp(t.get("timestamp", 0)),
            )
            for t in trades
        ]
        if is_sqlite(conn):
            sql = """
                INSERT OR IGNORE INTO trades (platform, market_id, external_trade_id, wallet,
                                    pseudonym, side, outcome, size, price, usdc_amount, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cur.executemany(sql, vals)
        else:
            if execute_values:
                execute_values(
                    cur,
                    """
                    INSERT INTO trades (platform, market_id, external_trade_id, wallet,
                                        pseudonym, side, outcome, size, price, usdc_amount, timestamp)
                    VALUES %s
                    ON CONFLICT (platform, external_trade_id)
                    DO NOTHING
                    """,
                    vals,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                )
            else:
                print("[DB] psycopg2 not available, skipping bulk trade insert.")
        conn.commit()
        print(f"   [DB] Inserted/ignored {len(vals)} trades")
    except Exception as e:
        conn.rollback()
        print(f"[DB] insert_trades error: {e}")
    finally:
        cur.close()


# ============================================================
# Polymarket fetchers
# ============================================================

def polymarket_search_markets(keywords: List[str], limit: int = 50) -> List[dict]:
    """Search Polymarket markets by keyword (best-effort via listing)."""
    all_markets = []
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"active": "true", "closed": "false", "limit": limit},
            timeout=20,
        )
        resp.raise_for_status()
        markets = resp.json()
    except Exception as e:
        print(f"[Polymarket] Failed to fetch markets: {e}")
        return []

    kw_lower = [k.lower() for k in keywords]
    for m in markets:
        q = (m.get("question") or "").lower()
        if any(kw in q for kw in kw_lower):
            try:
                prices = json.loads(m.get("outcomePrices", "[]")) if m.get("outcomePrices") else []
                outcomes = json.loads(m.get("outcomes", "[]")) if m.get("outcomes") else []
            except Exception:
                prices = []
                outcomes = []
            all_markets.append({
                "external_id": m["conditionId"],
                "slug": m.get("slug"),
                "question": m["question"],
                "category": m.get("category"),
                "outcomes": outcomes,
                "outcome_prices": prices,
                "volume": float(m.get("volume", 0) or 0),
                "liquidity": float(m.get("liquidityNum", 0) or 0),
                "active": m.get("active", True),
                "closed": m.get("closed", False),
                "end_date": m.get("endDate"),
                "best_bid": float(m.get("bestBid", 0) or 0),
                "best_ask": float(m.get("bestAsk", 0) or 0),
            })
    return all_markets


def polymarket_top_markets(limit: int = 5) -> List[dict]:
    """Fetch top markets by volume."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"active": "true", "closed": "false", "limit": limit},
            timeout=20,
        )
        resp.raise_for_status()
        markets = resp.json()
    except Exception as e:
        print(f"[Polymarket] Failed to fetch top markets: {e}")
        return []

    # Sort by volume descending
    markets.sort(key=lambda m: float(m.get("volume", 0) or 0), reverse=True)

    result = []
    for m in markets[:limit]:
        try:
            prices = json.loads(m.get("outcomePrices", "[]")) if m.get("outcomePrices") else []
            outcomes = json.loads(m.get("outcomes", "[]")) if m.get("outcomes") else []
        except Exception:
            prices = []
            outcomes = []
        result.append({
            "external_id": m["conditionId"],
            "slug": m.get("slug"),
            "question": m["question"],
            "category": m.get("category"),
            "outcomes": outcomes,
            "outcome_prices": prices,
            "volume": float(m.get("volume", 0) or 0),
            "liquidity": float(m.get("liquidityNum", 0) or 0),
            "active": m.get("active", True),
            "closed": m.get("closed", False),
            "end_date": m.get("endDate"),
            "best_bid": float(m.get("bestBid", 0) or 0),
            "best_ask": float(m.get("bestAsk", 0) or 0),
        })
    return result


def polymarket_fetch_trades(condition_id: str, limit: int = 500) -> List[dict]:
    try:
        resp = requests.get(
            f"{DATA_API}/trades",
            params={"market": condition_id, "limit": limit},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"   [Polymarket] Trade fetch failed: {e}")
        return []


# ============================================================
# Kalshi fetchers (public endpoints, no key needed for basic data)
# ============================================================

def kalshi_fetch_events(limit: int = 20) -> List[dict]:
    """Fetch active Kalshi events. Public endpoint, no key required."""
    try:
        resp = requests.get(
            "https://api.elections.kalshi.com/public/events",
            params={"limit": limit, "status": "active"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("events", [])
    except Exception as e:
        print(f"[Kalshi] Failed to fetch events: {e}")
        return []


def kalshi_fetch_market(external_id: str) -> Optional[dict]:
    """Fetch a single Kalshi market (series) details."""
    try:
        resp = requests.get(
            f"https://api.elections.kalshi.com/public/series/{external_id}",
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[Kalshi] Failed to fetch market {external_id}: {e}")
        return None


def kalshi_search_markets(keywords: List[str], limit: int = 50) -> List[dict]:
    """Search Kalshi markets by keyword."""
    events = kalshi_fetch_events(limit)
    kw_lower = [k.lower() for k in keywords]
    matches = []
    for ev in events:
        title = (ev.get("title") or "").lower()
        if any(kw in title for kw in kw_lower):
            ticker = ev.get("ticker", "")
            detail = kalshi_fetch_market(ticker)
            time.sleep(REQUEST_DELAY)
            if detail:
                series = detail.get("series", {})
                markets = series.get("markets", [])
                if markets:
                    m = markets[0]
                    yes_price = m.get("yes_ask", 0) / 100 if m.get("yes_ask") else 0
                    matches.append({
                        "external_id": ticker,
                        "slug": ticker,
                        "question": ev.get("title", ""),
                        "category": ev.get("category", ""),
                        "outcomes": ["Yes", "No"],
                        "outcome_prices": [yes_price, 1 - yes_price],
                        "volume": float(series.get("volume", 0) or 0),
                        "liquidity": 0,
                        "active": True,
                        "closed": False,
                        "end_date": series.get("close_date"),
                        "best_bid": float(m.get("yes_bid", 0) or 0) / 100,
                        "best_ask": float(m.get("yes_ask", 0) or 0) / 100,
                    })
    return matches


def kalshi_top_markets(limit: int = 5) -> List[dict]:
    """Fetch top Kalshi markets by volume."""
    events = kalshi_fetch_events(limit * 3)
    events.sort(key=lambda e: float(e.get("volume", 0) or 0), reverse=True)

    result = []
    for ev in events[:limit]:
        ticker = ev.get("ticker", "")
        detail = kalshi_fetch_market(ticker)
        time.sleep(REQUEST_DELAY)
        if detail:
            series = detail.get("series", {})
            markets = series.get("markets", [])
            if markets:
                m = markets[0]
                yes_price = m.get("yes_ask", 0) / 100 if m.get("yes_ask") else 0
                result.append({
                    "external_id": ticker,
                    "slug": ticker,
                    "question": ev.get("title", ""),
                    "category": ev.get("category", ""),
                    "outcomes": ["Yes", "No"],
                    "outcome_prices": [yes_price, 1 - yes_price],
                    "volume": float(series.get("volume", 0) or 0),
                    "liquidity": 0,
                    "active": True,
                    "closed": False,
                    "end_date": series.get("close_date"),
                    "best_bid": float(m.get("yes_bid", 0) or 0) / 100,
                    "best_ask": float(m.get("yes_ask", 0) or 0) / 100,
                })
    return result


# ============================================================
# Main pipeline
# ============================================================

def run_fetcher():
    print("=" * 72)
    print("  Polymarket + Kalshi Daily Fetcher")
    print("=" * 72)

    today = date.today()
    conn = get_db_conn()
    if is_sqlite(conn):
        print("[INFO] Using local SQLite database (polymarket_data.db).")
    else:
        print("[INFO] Using PostgreSQL database.")

    # ---- 1) SPY / SPX / QQQ markets ----
    print("\n[1/4] Fetching equity index markets (SPY, SPX, QQQ)...")
    equity_markets = polymarket_search_markets(EQUITY_KEYWORDS, limit=30)
    print(f"   Polymarket: {len(equity_markets)} matches")

    kalshi_equity = kalshi_search_markets(EQUITY_KEYWORDS, limit=30)
    print(f"   Kalshi:     {len(kalshi_equity)} matches")

    # ---- 2) Top 5 trending markets ----
    print("\n[2/4] Fetching top 5 trending markets...")
    poly_top = polymarket_top_markets(limit=5)
    print(f"   Polymarket: {len(poly_top)} markets")
    for m in poly_top:
        print(f"     • {m['question'][:60]} | Vol: ${m['volume']:,.0f}")

    kalshi_top = kalshi_top_markets(limit=5)
    print(f"   Kalshi:     {len(kalshi_top)} markets")
    for m in kalshi_top:
        print(f"     • {m['question'][:60]} | Vol: ${m['volume']:,.0f}")

    # ---- 3) Store in DB ----
    print("\n[3/4] Saving to database...")
    all_markets = equity_markets + kalshi_equity + poly_top + kalshi_top
    # Deduplicate by platform + external_id
    seen = set()
    unique_markets = []
    for m in all_markets:
        key = ("polymarket" if m in (equity_markets + poly_top) else "kalshi", m["external_id"])
        if key not in seen:
            seen.add(key)
            unique_markets.append((key[0], m))

    stored_count = 0
    for platform, m in unique_markets:
        market_id = upsert_market(conn, platform, m)
        if market_id:
            snapshot = {
                "date": today,
                "outcome_prices": m.get("outcome_prices", []),
                "volume": m.get("volume", 0),
                "open_interest": 0,
                "spread": m.get("best_ask", 0) - m.get("best_bid", 0),
                "best_bid": m.get("best_bid", 0),
                "best_ask": m.get("best_ask", 0),
            }
            insert_snapshot(conn, market_id, snapshot)
            stored_count += 1

            # Fetch trades for Polymarket only (Kalshi needs API key)
            if platform == "polymarket":
                trades = polymarket_fetch_trades(m["external_id"], limit=200)
                if trades:
                    insert_trades(conn, market_id, trades)
                time.sleep(REQUEST_DELAY)

    print(f"   Stored {stored_count} markets with snapshots.")

    # ---- 4) Cross-market arbitrage scan ----
    print("\n[4/4] Scanning for cross-market arbitrage...")
    # Simple heuristic: same keyword in both platforms
    arb_count = 0
    for kw in ["trump", "biden", "fed", "election", "gta"]:
        poly_matches = [m for _, m in unique_markets if m["question"].lower().count(kw) > 0 and _ == "polymarket"]
        kalshi_matches = [m for _, m in unique_markets if m["question"].lower().count(kw) > 0 and _ == "kalshi"]
        for pm in poly_matches:
            for km in kalshi_matches:
                # Compare Yes prices if both have Yes/No
                try:
                    py = float(pm["outcome_prices"][0]) if pm.get("outcome_prices") else 0
                    ky = float(km["outcome_prices"][0]) if km.get("outcome_prices") else 0
                    spread = abs(py - ky)
                    if spread > 0.05:  # 5% threshold
                        print(f"   ARB: {kw.upper()} | Poly={py:.2f} Kalshi={ky:.2f} Spread={spread:.2f}")
                        arb_count += 1
                except Exception:
                    continue
    if arb_count == 0:
        print("   No significant spreads found today.")

    if conn:
        conn.close()

    print("\n" + "=" * 72)
    print(f"  Done. Date: {today} | Markets: {stored_count}")
    print("=" * 72)


if __name__ == "__main__":
    run_fetcher()
