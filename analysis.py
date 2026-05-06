"""
Polymarket Insider Signal — Cross-Sectional Analysis (Active Markets)
============================================================
Because the public data API does not archive trades for closed markets,
a true historical backtest is not possible without internal data access.

This script instead analyzes CURRENTLY ACTIVE markets to produce
interesting behavioral stats:
    - Score distribution across active whales
    - Flag prevalence (burner accounts, concentration, spikes)
    - Correlation between suspicion score and bet characteristics
    - Side-bias: do HIGH wallets cluster on one outcome?

Usage:
    python3 analysis.py

Dependencies: requests
============================================================
"""

import os
import requests
import time
from typing import Optional, Dict, List

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")


def send_slack_alert(high_wallets: List[dict], total_analyzed: int, markets_count: int) -> None:
    """Send a formatted Slack alert when HIGH-suspicion wallets are detected."""
    if not SLACK_WEBHOOK_URL:
        print("   [Slack] SLACK_WEBHOOK_URL not set, skipping alert.")
        return

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 Polymarket Insider Alert — {len(high_wallets)} HIGH wallet(s) detected",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Analyzed *{total_analyzed}* whales across *{markets_count}* active markets.",
            },
        },
        {"type": "divider"},
    ]

    for r in high_wallets[:5]:
        flag_text = " • ".join(r["flags"]) if r["flags"] else "None"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Score: {r['score']}/100* — `{r['pseudonym']}`\n"
                        f"Market: {r['market'][:60]}\n"
                        f"Bet: ${r['target_volume']:,.0f} → *{r['dominant_outcome']}*\n"
                        f"Age: {r['account_age_days']:.0f}d | Trades: {r['total_trades']}\n"
                        f"Flags: {flag_text}"
                    ),
                },
            }
        )
        blocks.append({"type": "divider"})

    payload = {"blocks": blocks}
    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        print("   [Slack] Alert sent successfully.")
    except Exception as e:
        print(f"   [Slack] Failed to send alert: {e}")

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

MARKETS_TO_ANALYZE = 10
TOP_N_TRADERS = 10
MIN_TRADE_USDC = 100
USER_TRADES_LIMIT = 500
HIGH_THRESHOLD = 60
MEDIUM_THRESHOLD = 30
REQUEST_DELAY = 0.25


def fetch_active_markets(limit: int = 15) -> List[dict]:
    """Fetch active markets sorted by volume."""
    print(f"Fetching up to {limit} active markets...")
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"active": "true", "closed": "false", "limit": limit},
            timeout=20,
        )
        resp.raise_for_status()
        markets = resp.json()
        markets = [m for m in markets if float(m.get("volume", "0")) > 5000 and not m.get("closed")]
        markets.sort(key=lambda m: float(m.get("volume", "0")), reverse=True)
        print(f"   {len(markets)} active markets with volume > $5k")
        return markets
    except Exception as e:
        print(f"   Error: {e}")
        return []


def fetch_market_trades(condition_id: str) -> List[dict]:
    try:
        r = requests.get(
            f"{DATA_API}/trades", params={"market": condition_id, "limit": 500}, timeout=30
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def add_usdc(trades: List[dict]) -> List[dict]:
    for t in trades:
        try:
            t["_usdc"] = float(t.get("size", 0)) * float(t.get("price", 0))
        except (ValueError, TypeError):
            t["_usdc"] = 0
    return trades


def top_traders(trades: List[dict], min_usdc: float, top_n: int) -> List[dict]:
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


def fetch_user_history(address: str, limit: int = USER_TRADES_LIMIT) -> List[dict]:
    try:
        r = requests.get(f"{DATA_API}/trades", params={"user": address, "limit": limit}, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def compute_behavioral_features(
    history: List[dict], target_volume: float, cutoff_ts: float
) -> Optional[Dict]:
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

    total_volume_with_target = total_volume + target_volume
    target_concentration = (
        target_volume / total_volume_with_target if total_volume_with_target > 0 else 0
    )
    position_spike = target_volume / avg_position if avg_position > 0 else 0
    diversification = unique_events / total_trades if total_trades > 0 else 0

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
        "HIGH"
        if score >= HIGH_THRESHOLD
        else "MEDIUM"
        if score >= MEDIUM_THRESHOLD
        else "LOW"
        if score >= 15
        else "CLEAN"
    )
    return {"score": score, "flags": flags, "verdict": verdict}


def dominant_outcome(outcomes: Dict[str, float]) -> str:
    if not outcomes:
        return "?"
    return max(outcomes.items(), key=lambda x: x[1])[0]


def run_analysis():
    print("=" * 72)
    print("  Polymarket Insider Signal — Cross-Sectional Analysis")
    print("=" * 72)

    markets = fetch_active_markets(MARKETS_TO_ANALYZE + 5)
    markets = markets[:MARKETS_TO_ANALYZE]
    records = []

    for idx, market in enumerate(markets, 1):
        print(f"\n[{idx}/{len(markets)}] {market['question'][:55]}")
        trades = fetch_market_trades(market["conditionId"])
        trades = add_usdc(trades)
        print(f"    Trades: {len(trades)}")
        if len(trades) < 5:
            continue

        whales = top_traders(trades, MIN_TRADE_USDC, TOP_N_TRADERS)
        print(f"    Whales: {len(whales)}")
        if not whales:
            continue

        for w in whales:
            cutoff = w["first_ts"]
            history = fetch_user_history(w["address"])
            time.sleep(REQUEST_DELAY)
            if not history:
                continue

            f = compute_behavioral_features(history, w["target_volume"], cutoff)
            if not f:
                continue

            b = behavioral_score(f)
            dom = dominant_outcome(w["outcomes"])

            records.append(
                {
                    "market": market["question"],
                    "address": w["address"],
                    "pseudonym": w["pseudonym"],
                    "target_volume": w["target_volume"],
                    "dominant_outcome": dom,
                    "score": b["score"],
                    "verdict": b["verdict"],
                    "flags": b["flags"],
                    **f,
                }
            )

    if not records:
        print("\nNo records generated.")
        return

    print("\n" + "=" * 72)
    print("  SCORE DISTRIBUTION")
    print("=" * 72)

    tiers = {"HIGH": [], "MEDIUM": [], "LOW": [], "CLEAN": []}
    for r in records:
        tiers[r["verdict"]].append(r)

    for tier, rows in tiers.items():
        if not rows:
            continue
        avg_vol = sum(r["target_volume"] for r in rows) / len(rows)
        avg_age = sum(r["account_age_days"] for r in rows) / len(rows)
        avg_trades = sum(r["total_trades"] for r in rows) / len(rows)
        print(f"\n  {tier}: n={len(rows)}")
        print(f"    avg_bet=${avg_vol:,.0f}  avg_age={avg_age:.0f}d  avg_trades={avg_trades:.0f}")

    print("\n" + "=" * 72)
    print("  FLAG PREVALENCE")
    print("=" * 72)

    all_flags = {}
    for r in records:
        for fl in r["flags"]:
            all_flags[fl] = all_flags.get(fl, 0) + 1
    for fl, cnt in sorted(all_flags.items(), key=lambda x: x[1], reverse=True):
        pct = cnt / len(records) * 100
        print(f"    {fl:<40} {cnt:>3} / {len(records)} ({pct:.0f}%)")

    print("\n" + "=" * 72)
    print("  SIDE-BIAS BY TIER")
    print("=" * 72)

    for tier in ["HIGH", "MEDIUM", "LOW"]:
        rows = tiers[tier]
        if not rows:
            continue
        outcomes = {}
        for r in rows:
            oc = r["dominant_outcome"]
            outcomes[oc] = outcomes.get(oc, 0) + 1
        print(f"\n  {tier} wallets bet on:")
        for oc, cnt in sorted(outcomes.items(), key=lambda x: x[1], reverse=True)[:5]:
            pct = cnt / len(rows) * 100
            print(f"    {oc:<25} {cnt:>2} ({pct:.0f}%)")

    print("\n" + "=" * 72)
    print("  TOP 10 MOST SUSPICIOUS WALLETS (CURRENTLY ACTIVE)")
    print("=" * 72)

    records.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(records[:10], 1):
        print(f"\n  #{i}  Score: {r['score']}/100  {r['verdict']}")
        print(f"      Trader:    {r['pseudonym']}")
        print(f"      Market:    {r['market'][:50]}")
        print(f"      Bet:       ${r['target_volume']:,.0f} -> {r['dominant_outcome']}")
        print(f"      Age:       {r['account_age_days']:.0f}d  Trades: {r['total_trades']}")
        print(f"      Flags:     {', '.join(r['flags']) if r['flags'] else 'None'}")

    # ---- Slack alert ----
    high_wallets = tiers.get("HIGH", [])
    if high_wallets:
        send_slack_alert(high_wallets, len(records), len(markets))
    else:
        print("\n  [Slack] No HIGH wallets today, no alert sent.")

    print("\n" + "=" * 72)
    print(f"  Done. Profiled {len(records)} whales across {len(markets)} active markets.")
    print("=" * 72)


if __name__ == "__main__":
    run_analysis()
