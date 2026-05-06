"""
Add a specific Polymarket market to the database
Usage:
    python add_market.py https://polymarket.com/event/will-spy-close-up
    python add_market.py will-spy-close-up
"""

import os
import sys
import re
import json
from datetime import date

import requests

from local_db import get_db_conn
from fetcher import upsert_market, insert_snapshot

GAMMA_API = "https://gamma-api.polymarket.com"


def extract_slug(url_or_slug: str) -> str:
    """Extract slug from full URL or return as-is."""
    match = re.search(r'polymarket\.com/(?:event|market)/([^/?#]+)', url_or_slug)
    if match:
        return match.group(1)
    return url_or_slug.strip()


def fetch_by_slug(slug: str):
    """Fetch single market by slug from Polymarket."""
    try:
        # Try direct slug match in listing
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"active": "true", "closed": "false", "limit": 500},
            timeout=30,
        )
        resp.raise_for_status()
        markets = resp.json()
        for m in markets:
            if m.get("slug") == slug or slug in (m.get("slug") or ""):
                return m
    except Exception as e:
        print(f"[Search] {e}")
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python add_market.py <polymarket_url_or_slug>")
        print("Examples:")
        print('  python add_market.py https://polymarket.com/event/will-spy-close-up')
        print('  python add_market.py will-spy-close-up')
        sys.exit(1)

    raw = sys.argv[1]
    slug = extract_slug(raw)
    print(f"🔍 Searching Polymarket for: {slug}")

    market = fetch_by_slug(slug)
    if not market:
        print("❌ Market not found. It may be closed or the slug is incorrect.")
        sys.exit(1)

    print(f"✅ Found: {market['question']}")
    print(f"   Volume: ${float(market.get('volume',0) or 0):,.0f}")

    # Parse JSON fields
    try:
        prices = json.loads(market.get("outcomePrices", "[]")) if market.get("outcomePrices") else []
        outcomes = json.loads(market.get("outcomes", "[]")) if market.get("outcomes") else []
    except Exception:
        prices = []
        outcomes = []

    data = {
        "external_id": market["conditionId"],
        "slug": market.get("slug"),
        "question": market["question"],
        "category": market.get("category") or "Financials",
        "outcomes": outcomes,
        "outcome_prices": prices,
        "volume": float(market.get("volume", 0) or 0),
        "liquidity": float(market.get("liquidityNum", 0) or 0),
        "active": market.get("active", True),
        "closed": market.get("closed", False),
        "end_date": market.get("endDate"),
        "best_bid": float(market.get("bestBid", 0) or 0),
        "best_ask": float(market.get("bestAsk", 0) or 0),
    }

    conn = get_db_conn()
    market_id = upsert_market(conn, "polymarket", data)
    if market_id:
        snapshot = {
            "date": date.today(),
            "outcome_prices": data.get("outcome_prices", []),
            "volume": data.get("volume", 0),
            "open_interest": 0,
            "spread": data.get("best_ask", 0) - data.get("best_bid", 0),
            "best_bid": data.get("best_bid", 0),
            "best_ask": data.get("best_ask", 0),
        }
        insert_snapshot(conn, market_id, snapshot)
        print(f"✅ Saved to database (market_id={market_id})")
        print("   Refresh your Dashboard to see it!")
    else:
        print("❌ Failed to save to database.")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
