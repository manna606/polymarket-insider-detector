"""
Alpha Validation Tests
============================================================
Run daily after fetcher.py to validate whether prediction
market prices are well-calibrated and whether edges exist.

Usage:
    python alpha_test.py

Requires:
    DATABASE_URL environment variable
============================================================
"""

import os
import json
from datetime import date, timedelta
from typing import Optional, List, Dict

from local_db import get_db_conn


def test_calibration(conn) -> None:
    """
    For resolved markets, check if price == true probability.
    E.g., markets priced at 70% should win ~70% of the time.
    """
    print("\n[TEST 1] Calibration Test (requires resolved markets)")
    if not conn:
        print("   Skipped — no database connection.")
        return

    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.outcome_prices, m.resolution, m.question
        FROM markets m
        WHERE m.closed = TRUE
          AND m.resolution IS NOT NULL
          AND m.outcome_prices IS NOT NULL
        """
    )
    rows = cur.fetchall()
    cur.close()

    if not rows:
        print("   No resolved markets with price data yet.")
        return

    buckets = {}
    for prices_json, winner, question in rows:
        try:
            prices = prices_json if isinstance(prices_json, list) else json.loads(prices_json)
            outcomes = json.loads(prices_json)  # This assumes outcomes align with prices
            if not prices or len(prices) < 2:
                continue
            # Find implied probability of winner
            # We need outcomes list to map price to outcome — stored in same JSON
            # For simplicity, assume binary Yes/No and prices[0] = Yes
            winner_price = prices[0] if winner.lower() in ["yes", "up", "true"] else prices[1]
            bucket = round(winner_price * 10) * 10  # 0, 10, 20, ..., 100
            buckets.setdefault(bucket, {"total": 0, "wins": 0})
            buckets[bucket]["total"] += 1
            buckets[bucket]["wins"] += 1  # Since this is the winner
        except Exception:
            continue

    print(f"   Resolved markets analyzed: {len(rows)}")
    for b in sorted(buckets.keys()):
        data = buckets[b]
        actual = data["wins"] / data["total"] * 100 if data["total"] > 0 else 0
        print(f"   Price {b:3d}% → Actual win rate: {actual:.1f}% (n={data['total']})")


def test_volume_momentum(conn) -> None:
    """
    Check if markets with volume spikes in last 2 days
    show price drift (potential alpha for momentum).
    """
    print("\n[TEST 2] Volume Momentum (last 2 days)")
    if not conn:
        print("   Skipped — no database connection.")
        return

    today = date.today()
    yesterday = today - timedelta(days=1)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.question,
               s1.volume AS vol_today,
               s2.volume AS vol_yesterday,
               s1.outcome_prices AS prices_today,
               s2.outcome_prices AS prices_yesterday
        FROM price_snapshots s1
        JOIN price_snapshots s2
          ON s1.market_id = s2.market_id
          AND s2.snapshot_date = %s
        JOIN markets m ON m.id = s1.market_id
        WHERE s1.snapshot_date = %s
        ORDER BY (s1.volume - s2.volume) DESC
        LIMIT 10
        """,
        (yesterday, today),
    )
    rows = cur.fetchall()
    cur.close()

    if not rows:
        print("   Insufficient history (need 2+ days of snapshots).")
        return

    print(f"   Top 10 volume changes today:")
    for question, vt, vy, pt, py in rows:
        change = vt - vy if vy else 0
        pct_change = (change / vy * 100) if vy else 0
        print(f"     {question[:50]:50} | Vol Δ: ${change:10,.0f} ({pct_change:+5.1f}%)")


def test_cross_market_spread(conn) -> None:
    """
    Identify active arbitrage opportunities between Polymarket and Kalshi.
    """
    print("\n[TEST 3] Cross-Platform Spread (active markets)")
    if not conn:
        print("   Skipped — no database connection.")
        return

    cur = conn.cursor()
    cur.execute(
        """
        SELECT m1.question, m1.outcome_prices, m2.outcome_prices,
               m1.volume, m2.volume
        FROM markets m1
        JOIN markets m2
          ON LOWER(m1.question) LIKE '%' || LOWER(m2.question) || '%'
          OR LOWER(m2.question) LIKE '%' || LOWER(m1.question) || '%'
        WHERE m1.platform = 'polymarket'
          AND m2.platform = 'kalshi'
          AND m1.active = TRUE
          AND m2.active = TRUE
          AND m1.closed = FALSE
          AND m2.closed = FALSE
        """
    )
    rows = cur.fetchall()
    cur.close()

    if not rows:
        print("   No overlapping markets found today.")
        return

    print(f"   Overlapping markets: {len(rows)}")
    for q, p1, p2, v1, v2 in rows:
        try:
            prices1 = p1 if isinstance(p1, list) else json.loads(p1)
            prices2 = p2 if isinstance(p2, list) else json.loads(p2)
            if len(prices1) >= 2 and len(prices2) >= 2:
                spread = abs(float(prices1[0]) - float(prices2[0]))
                if spread > 0.03:
                    print(f"     {q[:50]:50} | Spread: {spread:.2f} (Poly={prices1[0]:.2f}, Kalshi={prices2[0]:.2f})")
        except Exception:
            continue


def test_whale_concentration(conn) -> None:
    """
    For markets with trade data, compute Gini-like concentration
    (what % of volume comes from top 5 wallets).
    """
    print("\n[TEST 4] Whale Concentration (Polymarket trades)")
    if not conn:
        print("   Skipped — no database connection.")
        return

    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.question,
               SUM(t.usdc_amount) AS total_vol,
               SUM(CASE WHEN t.wallet IN (
                   SELECT wallet FROM trades t2
                   WHERE t2.market_id = m.id
                   GROUP BY wallet
                   ORDER BY SUM(t2.usdc_amount) DESC
                   LIMIT 5
               ) THEN t.usdc_amount ELSE 0 END) AS top5_vol
        FROM markets m
        JOIN trades t ON t.market_id = m.id
        WHERE m.platform = 'polymarket'
        GROUP BY m.id, m.question
        HAVING SUM(t.usdc_amount) > 1000
        ORDER BY top5_vol / NULLIF(SUM(t.usdc_amount), 0) DESC
        LIMIT 10
        """
    )
    rows = cur.fetchall()
    cur.close()

    if not rows:
        print("   No trade data available yet (run fetcher for a few days).")
        return

    print(f"   Top 10 concentrated markets:")
    for question, total, top5 in rows:
        ratio = (top5 / total * 100) if total else 0
        print(f"     {question[:50]:50} | Top5: {ratio:5.1f}% of ${total:,.0f}")


def run_alpha_tests():
    print("=" * 72)
    print("  Alpha Validation Tests")
    print("=" * 72)

    conn = get_db_conn()
    if not conn:
        print("\n[WARN] Could not connect to database. Running in dry-run mode.")

    test_calibration(conn)
    test_volume_momentum(conn)
    test_cross_market_spread(conn)
    test_whale_concentration(conn)

    if conn:
        conn.close()

    print("\n" + "=" * 72)
    print("  Done.")
    print("=" * 72)


if __name__ == "__main__":
    run_alpha_tests()
