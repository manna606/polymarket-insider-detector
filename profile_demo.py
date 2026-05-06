"""
Polymarket Insider Detector — Demo v0.4 (BEHAVIORAL PROFILE)
============================================================
v0.4 upgrade: no longer depends on on-chain data; uses Polymarket
              user-behavior features instead.

Why the change?
    v0.3 discovered Polymarket uses proxy wallets, making on-chain
    nonce / balance useless. We switched to "user historical trading
    behavior" profiling — more stable and more signal-rich.

Workflow:
    1) Input a Polymarket event (URL or slug)
    2) Find the Top N whales on that event
    3) Pull full trade history for each whale (up to 500 trades)
    4) Compute 5 behavioral features:
       - account age (account_age_days)
       - burner vs pro trader (total_trades)
       - concentration on the target event (target_concentration)
       - position size spike (position_spike)
       - diversification (diversification)
    5) Composite "behavioral suspicion score" + triggered flags

Usage:
    python3 profile_demo.py

Dependencies: requests (only dependency)
============================================================
"""

import requests
import time
from typing import Optional, Dict, List


# ============================================================
# Config
# ============================================================

EVENT_INPUT = "https://polymarket.com/event/spx-up-or-down-on-april-30-2026"

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

TRADES_PER_MARKET = 500    # how many trades to pull from target event to find whales
TOP_N_TRADERS = 8          # analyze Top N whales (each needs history pull, so keep small)
MIN_TRADE_USDC = 100       # large-trade threshold
USER_TRADES_LIMIT = 500    # how many historical trades to pull per user


# ============================================================
# 1) Event query (same as v0.3)
# ============================================================

def parse_event_input(s: str) -> str:
    s = s.strip().rstrip("/")
    return s.split("/")[-1] if s.startswith("http") else s


def fetch_event(slug: str) -> Optional[dict]:
    print(f"Looking up event: {slug}")
    try:
        resp = requests.get(f"{GAMMA_API}/events",
                            params={"slug": slug}, timeout=20)
        resp.raise_for_status()
        events = resp.json()
        if not events:
            print(f"   Event not found")
            return None
        e = events[0]
        print(f"   OK: {e.get('title')}")
        print(f"     volume=${float(e.get('volume', 0)):,.0f}  "
              f"closed={e.get('closed')}")
        return e
    except Exception as ex:
        print(f"   Error: {ex}")
        return None


def fetch_event_trades(event: dict) -> List[dict]:
    all_trades = []
    for m in event.get("markets", []):
        cid = m.get("conditionId")
        if not cid:
            continue
        try:
            r = requests.get(f"{DATA_API}/trades",
                             params={"market": cid,
                                     "limit": TRADES_PER_MARKET},
                             timeout=30)
            r.raise_for_status()
            all_trades.extend(r.json())
        except Exception as e:
            print(f"   Market {cid[:10]} failed: {e}")
    return all_trades


# ============================================================
# 2) Identify Top whales (USDC = size * price)
# ============================================================

def add_usdc(trades: List[dict]) -> List[dict]:
    for t in trades:
        try:
            t["_usdc"] = float(t.get("size", 0)) * float(t.get("price", 0))
        except (ValueError, TypeError):
            t["_usdc"] = 0
    return trades


def top_traders_in_event(trades: List[dict],
                         min_usdc: float, top_n: int) -> List[dict]:
    """Aggregate by wallet, sort, and take Top N."""
    by_wallet: Dict[str, dict] = {}
    for t in trades:
        if t["_usdc"] < min_usdc:
            continue
        addr = t["proxyWallet"].lower()
        if addr not in by_wallet:
            by_wallet[addr] = {
                "address": t["proxyWallet"],
                "pseudonym": (t.get("pseudonym") or t.get("name")
                              or "anon"),
                "target_volume": 0.0,
                "target_trade_count": 0,
                "outcomes": {},
            }
        w = by_wallet[addr]
        w["target_volume"] += t["_usdc"]
        w["target_trade_count"] += 1
        oc = t.get("outcome", "?")
        w["outcomes"][oc] = w["outcomes"].get(oc, 0) + t["_usdc"]

    wallets = sorted(by_wallet.values(),
                     key=lambda x: x["target_volume"],
                     reverse=True)
    return wallets[:top_n]


# ============================================================
# 3) Pull a user's full trade history
# ============================================================

def fetch_user_history(address: str,
                       limit: int = USER_TRADES_LIMIT) -> List[dict]:
    try:
        r = requests.get(f"{DATA_API}/trades",
                         params={"user": address, "limit": limit},
                         timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"   History fetch failed for {address[:10]}..: {e}")
        return []


# ============================================================
# 4) Behavioral feature engineering (core innovation)
# ============================================================

def compute_behavioral_features(
    history: List[dict],
    target_event_slug: str,
    target_volume: float
) -> Optional[Dict]:
    """
    Extract 5 core behavioral features from a user's trade history.
    """
    if not history:
        return None

    history = add_usdc(history)
    history.sort(key=lambda t: t.get("timestamp", 0))

    # Basic stats
    total_volume = sum(t["_usdc"] for t in history)
    total_trades = len(history)
    unique_events = len(set(t.get("eventSlug", "") for t in history))
    unique_markets = len(set(t.get("conditionId", "") for t in history))

    # Time dimension
    now = time.time()
    timestamps = [t.get("timestamp", 0) for t in history]
    first_ts = min(timestamps) if timestamps else now
    last_ts = max(timestamps) if timestamps else now
    account_age_days = (now - first_ts) / 86400

    # Average / max position
    sizes = [t["_usdc"] for t in history if t["_usdc"] > 0]
    avg_position = sum(sizes) / len(sizes) if sizes else 0
    max_position = max(sizes) if sizes else 0

    # Concentration on the target event
    target_concentration = (target_volume / total_volume
                            if total_volume > 0 else 0)

    # Position spike: target event avg position vs historical avg
    target_trades_in_history = [
        t for t in history
        if t.get("eventSlug") == target_event_slug
    ]
    target_avg = (
        sum(t["_usdc"] for t in target_trades_in_history)
        / len(target_trades_in_history)
        if target_trades_in_history else 0
    )
    position_spike = target_avg / avg_position if avg_position > 0 else 0

    # Diversification: unique events / total trades
    # Lower -> more concentrated on a few events
    diversification = (unique_events / total_trades
                       if total_trades > 0 else 0)

    return {
        "total_volume": total_volume,
        "total_trades": total_trades,
        "unique_events": unique_events,
        "unique_markets": unique_markets,
        "account_age_days": account_age_days,
        "avg_position": avg_position,
        "max_position": max_position,
        "target_concentration": target_concentration,
        "target_avg_position": target_avg,
        "position_spike": position_spike,
        "diversification": diversification,
    }


# ============================================================
# 5) Behavioral suspicion score (0~100)
# ============================================================

def behavioral_score(f: Dict) -> Dict:
    score = 0
    flags = []

    # 1) Burner account (vs pro trader)
    if f["total_trades"] <= 5:
        score += 25
        flags.append("Burner account (<=5 trades)")
    elif f["total_trades"] <= 20:
        score += 12
        flags.append("Light usage (<=20 trades)")

    # 2) Account age
    if f["account_age_days"] < 7:
        score += 20
        flags.append(f"Brand new (<7d old)")
    elif f["account_age_days"] < 30:
        score += 10
        flags.append(f"New account (<30d old)")

    # 3) Highly concentrated on target event
    if f["target_concentration"] >= 0.7:
        score += 25
        flags.append(
            f"All-in on target ({f['target_concentration']*100:.0f}% of vol)"
        )
    elif f["target_concentration"] >= 0.3:
        score += 12
        flags.append(
            f"Concentrated on target "
            f"({f['target_concentration']*100:.0f}%)"
        )

    # 4) Abnormal position spike
    if f["position_spike"] >= 5:
        score += 20
        flags.append(
            f"Position {f['position_spike']:.1f}x normal"
        )
    elif f["position_spike"] >= 2:
        score += 10
        flags.append(
            f"Position {f['position_spike']:.1f}x normal"
        )

    # 5) Highly specialized (few events + large volume)
    if (f["diversification"] < 0.1 and f["total_trades"] > 50):
        score += 10
        flags.append("Specialist trader")

    score = min(score, 100)
    verdict = (
        "HIGH" if score >= 60
        else "MEDIUM" if score >= 30
        else "LOW" if score >= 15
        else "CLEAN"
    )
    return {"score": score, "flags": flags, "verdict": verdict}


# ============================================================
# 6) Report helpers
# ============================================================

def fmt_dominant_outcome(outcomes: Dict[str, float]) -> str:
    if not outcomes:
        return "?"
    best = max(outcomes.items(), key=lambda x: x[1])
    total = sum(outcomes.values())
    return f"{best[0]} ({best[1]/total*100:.0f}%)"


def fmt_days(d: float) -> str:
    if d < 1:
        return f"{d*24:.1f}h"
    elif d < 365:
        return f"{d:.0f}d"
    return f"{d/365:.1f}y"


# ============================================================
# 7) Main
# ============================================================

def main():
    print("=" * 76)
    print("  Polymarket Insider Detector — v0.4 (BEHAVIORAL)")
    print("=" * 76)
    print(f"  Target event: {EVENT_INPUT}\n")

    # ---- Step 1: Resolve event ----
    slug = parse_event_input(EVENT_INPUT)
    event = fetch_event(slug)
    if not event:
        return

    # ---- Step 2: Pull event trades, find Top whales ----
    print(f"\nFetching event trades, finding Top {TOP_N_TRADERS} whales...")
    raw = fetch_event_trades(event)
    raw = add_usdc(raw)
    print(f"   Total trades: {len(raw)}")

    top = top_traders_in_event(raw, MIN_TRADE_USDC, TOP_N_TRADERS)
    print(f"   Top {len(top)} whales locked\n")

    if not top:
        print("No large trades, exiting")
        return

    # ---- Step 3: Behavioral profile for each whale ----
    print("Pulling full trade history for each whale...")
    print("   (this will call Polymarket API multiple times, please wait)\n")

    results = []
    for i, w in enumerate(top, 1):
        print(f"   [{i}/{len(top)}] {w['address'][:10]}.. "
              f"({w['pseudonym']:<22}) "
              f"target event bet ${w['target_volume']:,.0f}")

        history = fetch_user_history(w["address"])
        time.sleep(0.3)

        if not history:
            print("       History fetch failed")
            continue

        f = compute_behavioral_features(
            history, slug, w["target_volume"]
        )
        if not f:
            continue

        bscore = behavioral_score(f)

        print(f"       History: {f['total_trades']} trades, "
              f"{f['unique_events']} events, "
              f"vol=${f['total_volume']:,.0f}, "
              f"age={fmt_days(f['account_age_days'])}")
        print(f"       Behavioral score: {bscore['score']}/100  "
              f"{bscore['verdict']}")

        results.append({**w, **f, **bscore})

    # ---- Step 4: Output ranking ----
    if not results:
        print("\nNo results")
        return

    results.sort(key=lambda x: x["score"], reverse=True)

    print("\n" + "=" * 76)
    print(f"  Behavioral suspicion ranking — {event.get('title', '?')}")
    print("=" * 76)

    for i, r in enumerate(results, 1):
        flag = ("🔴" if r["score"] >= 60
                else "🟡" if r["score"] >= 30 else "🟢")
        print(f"\n  {flag}  #{i}  {r['verdict']}  "
              f"Behavioral Score: {r['score']}/100")
        print(f"      Address:      {r['address']}")
        print(f"      Trader:       {r['pseudonym']}")
        print(f"      Bet on event: ${r['target_volume']:,.0f}  "
              f"({r['target_trade_count']} trades) "
              f"- {fmt_dominant_outcome(r['outcomes'])}")
        print(f"      --- Profile ---")
        print(f"      Total volume:    ${r['total_volume']:,.0f}  "
              f"({r['total_trades']} trades)")
        print(f"      Account age:     {fmt_days(r['account_age_days'])}")
        print(f"      Unique events:   {r['unique_events']}")
        print(f"      Avg position:    ${r['avg_position']:,.2f}  "
              f"(max ${r['max_position']:,.0f})")
        print(f"      Concentration:   "
              f"{r['target_concentration']*100:.1f}% on target event")
        print(f"      Position spike:  {r['position_spike']:.2f}x normal")
        print(f"      Diversification: {r['diversification']:.3f}  "
              f"(events/trade)")
        if r["flags"]:
            print(f"      Flags:")
            for fl in r["flags"]:
                print(f"        - {fl}")

    # ---- Step 5: HIGH SUSPICION highlight ----
    high = [r for r in results if r["score"] >= 60]
    if high:
        print("\n" + "=" * 76)
        print(f"  HIGH SUSPICION — {len(high)} wallet(s) match insider profile:")
        print("=" * 76)
        for r in high:
            print(f"     - {r['address']}  ({r['pseudonym']})")
            print(f"       Betting {fmt_dominant_outcome(r['outcomes'])} "
                  f"${r['target_volume']:,.0f}")
            for fl in r["flags"]:
                print(f"       - {fl}")

    print("\n" + "=" * 76)
    print(f"  Done! Profiled {len(results)} whales")
    print("=" * 76)


if __name__ == "__main__":
    main()
