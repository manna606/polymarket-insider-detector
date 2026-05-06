"""
Polymarket Insider Signal — Backtest (v0.1)
============================================================
Statistical validation: does the v0.4 behavioral suspicion score
actually predict winners on resolved Polymarket events?

Methodology (per BACKTEST_DESIGN.md):
    1) Fetch resolved events with known winning outcome
    2) For each event, fetch all trades and identify top whales
    3) For each whale, fetch their trade history up to event close
    4) Compute behavioral score using only pre-close history
    5) Check if their dominant bet outcome == winning outcome
    6) Compare HIGH-score hit rate vs random baseline

Usage:
    python3 backtest.py

Dependencies: requests
============================================================
"""

import requests
import time
import json
import random
from datetime import datetime
from typing import Optional, Dict, List

# ============================================================
# Config
# ============================================================

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

EVENTS_TO_TEST = 18          # number of closed events to analyze
TOP_N_TRADERS = 10           # top whales per event
MIN_TRADE_USDC = 100         # whale threshold
USER_TRADES_LIMIT = 500      # history depth per user
HIGH_THRESHOLD = 60          # score >= 60 = HIGH
MEDIUM_THRESHOLD = 30        # score >= 30 = MEDIUM
BASELINE_DRAWS = 500         # Monte Carlo draws for null distribution
REQUEST_DELAY = 0.25         # seconds between API calls

random.seed(42)


# ============================================================
# 1) Fetch resolved events
# ============================================================

def fetch_resolved_events(limit: int = 50) -> List[dict]:
    """Fetch closed events where one outcome clearly won (price > 0.95)."""
    print(f"Fetching up to {limit} closed events...")
    try:
        resp = requests.get(f"{GAMMA_API}/events",
                            params={"closed": "true", "limit": limit},
                            timeout=20)
        resp.raise_for_status()
        events = resp.json()
    except Exception as e:
        print(f"   Failed to fetch events: {e}")
        return []

    resolved = []
    for e in events:
        winner = None
        for m in e.get("markets", []):
            ps = m.get("outcomePrices")
            if not ps:
                continue
            try:
                prices = [float(x) for x in json.loads(ps)]
                outcomes = json.loads(m.get("outcomes", "[]"))
                if len(prices) >= 2 and max(prices) > 0.95 and min(prices) < 0.05:
                    winner = outcomes[prices.index(max(prices))]
                    break
            except Exception:
                continue
        if winner:
            resolved.append({
                "title": e["title"],
                "slug": e["slug"],
                "winner": winner,
                "markets": e.get("markets", []),
                "volume": float(e.get("volume", 0)),
            })
    print(f"   {len(resolved)} clearly resolved events found")
    return resolved


# ============================================================
# 2) Fetch trades for an event
# ============================================================

def fetch_event_trades(event: dict) -> List[dict]:
    """Pull all trades across all markets in the event."""
    all_trades = []
    for m in event.get("markets", []):
        cid = m.get("conditionId")
        if not cid:
            continue
        try:
            r = requests.get(f"{DATA_API}/trades",
                             params={"market": cid, "limit": 500},
                             timeout=30)
            r.raise_for_status()
            all_trades.extend(r.json())
        except Exception:
            continue
        time.sleep(REQUEST_DELAY)
    return all_trades


def add_usdc(trades: List[dict]) -> List[dict]:
    for t in trades:
        try:
            t["_usdc"] = float(t.get("size", 0)) * float(t.get("price", 0))
        except (ValueError, TypeError):
            t["_usdc"] = 0
    return trades


def top_traders(trades: List[dict], min_usdc: float, top_n: int) -> List[dict]:
    """Aggregate by wallet and return top N whales."""
    by_wallet: Dict[str, dict] = {}
    for t in trades:
        if t.get("_usdc", 0) < min_usdc:
            continue
        addr = t.get("proxyWallet", "").lower()
        if not addr:
            continue
        if addr not in by_wallet:
            by_wallet[addr] = {
                "address": t["proxyWallet"],
                "pseudonym": t.get("pseudonym") or t.get("name") or "anon",
                "target_volume": 0.0,
                "target_trade_count": 0,
                "outcomes": {},
                "first_ts": float("inf"),
            }
        w = by_wallet[addr]
        w["target_volume"] += t["_usdc"]
        w["target_trade_count"] += 1
        oc = t.get("outcome", "?")
        w["outcomes"][oc] = w["outcomes"].get(oc, 0) + t["_usdc"]
        ts = t.get("timestamp", 0)
        if ts and ts < w["first_ts"]:
            w["first_ts"] = ts

    wallets = sorted(by_wallet.values(), key=lambda x: x["target_volume"], reverse=True)
    return wallets[:top_n]


def dominant_outcome(outcomes: Dict[str, float]) -> str:
    if not outcomes:
        return "?"
    return max(outcomes.items(), key=lambda x: x[1])[0]


# ============================================================
# 3) Fetch user history (pre-event)
# ============================================================

def fetch_user_history(address: str, limit: int = USER_TRADES_LIMIT) -> List[dict]:
    try:
        r = requests.get(f"{DATA_API}/trades",
                         params={"user": address, "limit": limit},
                         timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def compute_behavioral_features(
    history: List[dict],
    target_event_slug: str,
    target_volume: float,
    cutoff_ts: float,
) -> Optional[Dict]:
    """
    Compute behavioral features using only history BEFORE cutoff_ts.
    cutoff_ts is typically the user's first bet timestamp on the target event.
    """
    # Filter to pre-cutoff history (look-ahead bias control)
    history = [h for h in history if h.get("timestamp", 0) < cutoff_ts]
    history = add_usdc(history)
    history.sort(key=lambda t: t.get("timestamp", 0))

    if not history:
        return None

    total_volume = sum(t["_usdc"] for t in history)
    total_trades = len(history)
    unique_events = len(set(t.get("eventSlug", "") for t in history))

    now = cutoff_ts
    timestamps = [t.get("timestamp", 0) for t in history]
    first_ts = min(timestamps) if timestamps else now
    account_age_days = (now - first_ts) / 86400

    sizes = [t["_usdc"] for t in history if t["_usdc"] > 0]
    avg_position = sum(sizes) / len(sizes) if sizes else 0

    # target_concentration: how much of their lifetime volume is this event?
    # We add target_volume because at bet time, they have already placed this bet
    total_volume_with_target = total_volume + target_volume
    target_concentration = (
        target_volume / total_volume_with_target
        if total_volume_with_target > 0 else 0
    )

    # Position spike: average position on this event vs historical average
    # For simplicity, use target_volume / target_trade_count as event avg
    target_avg = target_volume  # simplified: treating as single bet for spike calc
    position_spike = target_avg / avg_position if avg_position > 0 else 0

    diversification = (unique_events / total_trades if total_trades > 0 else 0)

    return {
        "total_trades": total_trades,
        "unique_events": unique_events,
        "account_age_days": account_age_days,
        "avg_position": avg_position,
        "target_concentration": target_concentration,
        "position_spike": position_spike,
        "diversification": diversification,
    }


def behavioral_score(f: Dict) -> Dict:
    score = 0
    flags = []

    if f["total_trades"] <= 5:
        score += 25
        flags.append("Burner account (<=5 trades)")
    elif f["total_trades"] <= 20:
        score += 12
        flags.append("Light usage (<=20 trades)")

    if f["account_age_days"] < 7:
        score += 20
        flags.append("Brand new (<7d old)")
    elif f["account_age_days"] < 30:
        score += 10
        flags.append("New account (<30d old)")

    if f["target_concentration"] >= 0.7:
        score += 25
        flags.append(f"All-in ({f['target_concentration']*100:.0f}% of vol)")
    elif f["target_concentration"] >= 0.3:
        score += 12
        flags.append(f"Concentrated ({f['target_concentration']*100:.0f}%)")

    if f["position_spike"] >= 5:
        score += 20
        flags.append(f"Position {f['position_spike']:.1f}x normal")
    elif f["position_spike"] >= 2:
        score += 10
        flags.append(f"Position {f['position_spike']:.1f}x normal")

    if f["diversification"] < 0.1 and f["total_trades"] > 50:
        score += 10
        flags.append("Specialist trader")

    score = min(score, 100)
    verdict = (
        "HIGH" if score >= HIGH_THRESHOLD
        else "MEDIUM" if score >= MEDIUM_THRESHOLD
        else "LOW" if score >= 15
        else "CLEAN"
    )
    return {"score": score, "flags": flags, "verdict": verdict}


# ============================================================
# 4) Main backtest
# ============================================================

def run_backtest():
    print("=" * 72)
    print("  Polymarket Insider Signal — Backtest v0.1")
    print("=" * 72)

    # ---- Step 1: Load resolved events ----
    events = fetch_resolved_events(EVENTS_TO_TEST + 10)
    if len(events) < EVENTS_TO_TEST:
        print(f"Warning: only {len(events)} resolved events available")
    events = events[:EVENTS_TO_TEST]

    records = []          # one row per wallet-event
    event_wallet_lists = []  # for baseline draws

    for idx, event in enumerate(events, 1):
        print(f"\n[{idx}/{len(events)}] {event['title'][:55]}")
        print(f"    Winner: {event['winner']}")

        # Fetch event trades
        trades = fetch_event_trades(event)
        trades = add_usdc(trades)
        print(f"    Trades: {len(trades)}")
        if len(trades) < 5:
            continue

        whales = top_traders(trades, MIN_TRADE_USDC, TOP_N_TRADERS)
        print(f"    Whales: {len(whales)}")
        if not whales:
            continue

        event_rows = []
        for w in whales:
            # Look-ahead bias control: only use history before first bet on this event
            cutoff = w["first_ts"]
            history = fetch_user_history(w["address"])
            time.sleep(REQUEST_DELAY)

            if not history:
                continue

            f = compute_behavioral_features(
                history, event["slug"], w["target_volume"], cutoff
            )
            if not f:
                continue

            b = behavioral_score(f)
            dom = dominant_outcome(w["outcomes"])
            won = 1 if dom == event["winner"] else 0

            row = {
                "event": event["title"],
                "winner": event["winner"],
                "address": w["address"],
                "pseudonym": w["pseudonym"],
                "target_volume": w["target_volume"],
                "dominant_outcome": dom,
                "won": won,
                **f,
                **b,
            }
            records.append(row)
            event_rows.append(row)

        if event_rows:
            event_wallet_lists.append(event_rows)
            high = [r for r in event_rows if r["verdict"] == "HIGH"]
            print(f"    HIGH wallets this event: {len(high)} "
                  f"(hit rate: {sum(r['won'] for r in high)/len(high)*100:.0f}%" if high else "")

    # ---- Step 5: Aggregate statistics ----
    if not records:
        print("\nNo records generated. Exiting.")
        return

    print("\n" + "=" * 72)
    print("  RESULTS")
    print("=" * 72)

    tiers = {"HIGH": [], "MEDIUM": [], "LOW": [], "CLEAN": []}
    for r in records:
        tiers[r["verdict"]].append(r)

    for tier, rows in tiers.items():
        if not rows:
            continue
        hit = sum(r["won"] for r in rows) / len(rows)
        avg_vol = sum(r["target_volume"] for r in rows) / len(rows)
        print(f"\n  {tier}: n={len(rows)}  hit_rate={hit*100:.1f}%  avg_bet=${avg_vol:,.0f}")

    # ---- Step 6: Random baseline (Monte Carlo) ----
    # For each event, randomly sample the same number of HIGH wallets
    # from all wallets on that event, and compute their hit rate.
    high_obs = tiers["HIGH"]
    if high_obs:
        n_high = len(high_obs)
        baseline_rates = []
        for _ in range(BASELINE_DRAWS):
            draws = []
            for ev_rows in event_wallet_lists:
                if len(ev_rows) == 0:
                    continue
                k = len([r for r in ev_rows if r["verdict"] == "HIGH"])
                if k == 0:
                    continue
                sampled = random.choices(ev_rows, k=k)
                draws.extend(sampled)
            if draws:
                baseline_rates.append(sum(r["won"] for r in draws) / len(draws))

        if baseline_rates:
            actual_high_hit = sum(r["won"] for r in high_obs) / len(high_obs)
            baseline_mean = sum(baseline_rates) / len(baseline_rates)
            baseline_std = (
                (sum((x - baseline_mean) ** 2 for x in baseline_rates) / len(baseline_rates)) ** 0.5
            )
            print(f"\n  HIGH wallet hit rate:     {actual_high_hit*100:.1f}%")
            print(f"  Random baseline mean:     {baseline_mean*100:.1f}%")
            print(f"  Random baseline std:      {baseline_std*100:.1f}%")
            if baseline_std > 0:
                t = (actual_high_hit - baseline_mean) / baseline_std
                print(f"  t-statistic:              {t:.2f}")
                # Rough one-sided p-value from normal approximation
                from math import erf
                p = 0.5 * (1 - erf(t / (2 ** 0.5)))
                print(f"  Approx one-sided p:       {p:.3f}")
            else:
                print("  t-statistic:              N/A (zero variance)")

    # ---- Step 7: Notable examples ----
    print("\n" + "=" * 72)
    print("  NOTABLE EXAMPLES")
    print("=" * 72)

    high_won = [r for r in records if r["verdict"] == "HIGH" and r["won"] == 1]
    high_lost = [r for r in records if r["verdict"] == "HIGH" and r["won"] == 0]

    if high_won:
        print(f"\n  HIGH wallets that WON (n={len(high_won)}):")
        for r in high_won[:3]:
            print(f"    {r['pseudonym'][:20]:<20} ${r['target_volume']:>8,.0f} "
                  f"-> {r['dominant_outcome']:<20} ({r['event'][:40]})")

    if high_lost:
        print(f"\n  HIGH wallets that LOST (n={len(high_lost)}):")
        for r in high_lost[:3]:
            print(f"    {r['pseudonym'][:20]:<20} ${r['target_volume']:>8,.0f} "
                  f"-> {r['dominant_outcome']:<20} ({r['event'][:40]})")

    print("\n" + "=" * 72)
    print(f"  Done. Analyzed {len(records)} wallet-event observations "
          f"across {len(event_wallet_lists)} events.")
    print("=" * 72)


if __name__ == "__main__":
    run_backtest()
