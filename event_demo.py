"""
Polymarket Insider Detector — Demo v0.3 (EVENT-BASED)
============================================================
Smarter workflow: lock onto an event/market first, then analyze wallets
that traded on it.

Workflow:
    1) You provide a Polymarket event URL or slug
       e.g. https://polymarket.com/event/spx-up-or-down-on-april-30-2026
    2) The script automatically:
       - Finds all markets under this event
       - Pulls all trades for those markets
       - Sorts by size and picks the Top N whales
       - Runs on-chain profiling + suspicion scoring for each whale
    3) Output: a full "event -> whale -> suspicion score" report

Usage:
    python3 event_demo.py
    # or modify EVENT_INPUT to the event you want to analyze

Dependencies: requests (only dependency)
============================================================
"""

import requests
import time
from typing import Optional, Dict, List


# ============================================================
# 1) Polymarket event to analyze
# ------------------------------------------------------------
# Supports two input formats:
#   - Full URL: "https://polymarket.com/event/..."
#   - Slug only: "spx-up-or-down-on-april-30-2026"
# ============================================================

EVENT_INPUT = "https://polymarket.com/event/spx-up-or-down-on-april-30-2026"

# Fetch parameters
TRADES_PER_MARKET = 500       # how many trades to pull per market
TOP_N_TRADERS = 15            # final Top N whales to display
MIN_TRADE_USDC = 100          # minimum single-trade size (smaller ones ignored)


# ============================================================
# 2) API endpoints
# ============================================================

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
POLYGON_RPC = "https://polygon.drpc.org"


# ============================================================
# 3) Known whitelist (exchange / system addresses)
# ============================================================

KNOWN_ADDRESSES_LOWER = {
    "0x0000000000000000000000000000000000000000": "Zero Address",
    "0x0000000000000000000000000000000000000001": "Burn Address",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance 8",
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
}


# ============================================================
# 4) URL / slug parsing
# ============================================================

def parse_event_input(s: str) -> str:
    """Supports full URL or bare slug."""
    s = s.strip().rstrip("/")
    if s.startswith("http"):
        return s.split("/")[-1]
    return s


# ============================================================
# 5) Fetch event info
# ============================================================

def fetch_event(slug: str) -> Optional[dict]:
    """Look up event metadata by slug."""
    print(f"Looking up event: {slug}")
    try:
        resp = requests.get(f"{GAMMA_API}/events",
                            params={"slug": slug}, timeout=20)
        resp.raise_for_status()
        events = resp.json()
        if not events:
            print(f"   Event not found: '{slug}'")
            return None
        event = events[0]
        print(f"   Found: {event.get('title', '?')}")
        print(f"     ID:     {event.get('id')}")
        print(f"     Volume: ${float(event.get('volume', 0)):,.0f}")
        print(f"     Status: "
              f"{'closed' if event.get('closed') else 'active'}")
        markets = event.get("markets", [])
        print(f"     Markets under this event: {len(markets)}")
        return event
    except Exception as e:
        print(f"   Query failed: {e}")
        return None


# ============================================================
# 6) Fetch all trades for a market
# ============================================================

def fetch_trades_for_market(condition_id: str,
                            limit: int = 500) -> List[dict]:
    """Pull all trades for a market via its conditionId."""
    try:
        resp = requests.get(f"{DATA_API}/trades",
                            params={"market": condition_id,
                                    "limit": limit},
                            timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"   Trade fetch failed ({condition_id[:10]}): {e}")
        return []


def fetch_all_trades_for_event(event: dict) -> List[dict]:
    """Pull all trades across all markets under this event."""
    all_trades = []
    for market in event.get("markets", []):
        cid = market.get("conditionId")
        if not cid:
            continue
        trades = fetch_trades_for_market(cid, TRADES_PER_MARKET)
        print(f"   - {market.get('question', '?')[:50]:<50} "
              f"- {len(trades)} trades")
        all_trades.extend(trades)
    return all_trades


# ============================================================
# 7) Process trades: USDC sizing + filtering + aggregation
# ============================================================

def add_usdc_and_filter(trades: List[dict],
                        min_usdc: float = 100) -> List[dict]:
    """Compute USDC value per trade and filter out small ones."""
    out = []
    for t in trades:
        try:
            size = float(t.get("size", 0))
            price = float(t.get("price", 0))
            usdc = size * price
            if usdc < min_usdc:
                continue
            t["_usdc"] = usdc
            out.append(t)
        except (ValueError, TypeError):
            continue
    return out


def aggregate_by_wallet(trades: List[dict]) -> List[dict]:
    """
    Aggregate by wallet: total bet, total trade count, net direction.
    """
    by_wallet: Dict[str, dict] = {}
    for t in trades:
        addr = t["proxyWallet"].lower()
        if addr not in by_wallet:
            by_wallet[addr] = {
                "address": t["proxyWallet"],
                "pseudonym": (t.get("pseudonym") or t.get("name")
                              or "anon"),
                "total_usdc": 0.0,
                "trade_count": 0,
                "buy_usdc": 0.0,
                "sell_usdc": 0.0,
                "outcomes": {},  # outcome -> usdc
                "first_ts": t.get("timestamp", 0),
                "last_ts": t.get("timestamp", 0),
            }
        w = by_wallet[addr]
        w["total_usdc"] += t["_usdc"]
        w["trade_count"] += 1
        if t.get("side") == "BUY":
            w["buy_usdc"] += t["_usdc"]
        else:
            w["sell_usdc"] += t["_usdc"]
        oc = t.get("outcome", "?")
        w["outcomes"][oc] = w["outcomes"].get(oc, 0) + t["_usdc"]
        ts = t.get("timestamp", 0)
        w["first_ts"] = min(w["first_ts"], ts) if w["first_ts"] else ts
        w["last_ts"] = max(w["last_ts"], ts)
    return list(by_wallet.values())


# ============================================================
# 8) On-chain analysis (same as v0.1 / v0.2)
# ============================================================

def rpc_call(method: str, params: list) -> Optional[dict]:
    payload = {"jsonrpc": "2.0", "method": method,
               "params": params, "id": 1}
    try:
        resp = requests.post(POLYGON_RPC, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def get_nonce(addr: str) -> Optional[int]:
    r = rpc_call("eth_getTransactionCount", [addr, "latest"])
    return int(r["result"], 16) if r and "result" in r else None


def get_balance_matic(addr: str) -> Optional[float]:
    r = rpc_call("eth_getBalance", [addr, "latest"])
    return int(r["result"], 16) / 1e18 if r and "result" in r else None


def calculate_suspicion_score(nonce: int, balance: float,
                              total_usdc: float) -> Dict:
    fresh = (40 if nonce <= 5 else 25 if nonce <= 20
             else 10 if nonce <= 100 else 0)
    size = (30 if total_usdc >= 50000 else 20 if total_usdc >= 10000
            else 10 if total_usdc >= 1000 else 0)
    if balance > 0:
        ratio = total_usdc / max(balance, 0.01)
        ratio_score = (30 if ratio > 100 else 15 if ratio > 10 else 0)
    else:
        ratio_score = 30

    total = fresh + size + ratio_score
    verdict = ("HIGH" if total >= 70
               else "MEDIUM" if total >= 40
               else "LOW" if total >= 20
               else "CLEAN")
    return {
        "fresh_score": fresh,
        "size_score": size,
        "ratio_score": ratio_score,
        "total_score": total,
        "verdict": verdict,
    }


# ============================================================
# 9) Report helpers
# ============================================================

def fmt_dominant_outcome(outcomes: Dict[str, float]) -> str:
    """Return the outcome with the largest bet."""
    if not outcomes:
        return "?"
    best = max(outcomes.items(), key=lambda x: x[1])
    total = sum(outcomes.values())
    return f"{best[0]} ({best[1] / total * 100:.0f}%)"


# ============================================================
# 10) Main
# ============================================================

def main():
    print("=" * 72)
    print("  Polymarket Insider Detector — v0.3 (EVENT-BASED)")
    print("=" * 72)
    print(f"  Target event: {EVENT_INPUT}")
    print()

    # ---- Step 1: Resolve event ----
    slug = parse_event_input(EVENT_INPUT)
    event = fetch_event(slug)
    if not event:
        return

    # ---- Step 2: Fetch all relevant trades ----
    print("\nFetching trades for all markets...")
    raw_trades = fetch_all_trades_for_event(event)
    print(f"   Total raw trades: {len(raw_trades)}")

    if not raw_trades:
        print("No trade data, exiting")
        return

    # ---- Step 3: USDC sizing + filter small trades ----
    big = add_usdc_and_filter(raw_trades, MIN_TRADE_USDC)
    print(f"   After filtering (>= ${MIN_TRADE_USDC}): {len(big)} trades")

    # ---- Step 4: Aggregate by wallet ----
    wallets = aggregate_by_wallet(big)
    print(f"   Unique wallets involved: {len(wallets)}")

    # Exclude whitelist
    wallets = [w for w in wallets
               if w["address"].lower() not in KNOWN_ADDRESSES_LOWER]

    # Sort by total bet, take Top N
    wallets.sort(key=lambda x: x["total_usdc"], reverse=True)
    top = wallets[:TOP_N_TRADERS]
    print(f"   Top {len(top)} whales selected for on-chain analysis\n")

    # ---- Step 5: On-chain analysis for each whale ----
    print("On-chain analysis running...")
    print(f"   {'#':<3} {'Address':<14} {'Pseudonym':<22} "
          f"{'Volume':<12} {'Trades':<8} {'Outcome':<22}")

    results = []
    for i, w in enumerate(top, 1):
        nonce = get_nonce(w["address"])
        balance = get_balance_matic(w["address"])
        if nonce is None or balance is None:
            print(f"   {i:<3} {w['address'][:10]}..  "
                  f"{w['pseudonym'][:20]:<22} (RPC failed)")
            time.sleep(0.3)
            continue

        score = calculate_suspicion_score(
            nonce, balance, w["total_usdc"]
        )
        result = {**w, "nonce": nonce, "balance_matic": balance, **score}
        results.append(result)

        print(f"   {i:<3} {w['address'][:10]}..  "
              f"{w['pseudonym'][:20]:<22} "
              f"${w['total_usdc']:>9,.0f}  "
              f"{w['trade_count']:>4}    "
              f"{fmt_dominant_outcome(w['outcomes'])[:20]}")
        time.sleep(0.3)

    # ---- Step 6: Output suspicion ranking ----
    if not results:
        print("\nNo wallets were successfully analyzed")
        return

    results.sort(key=lambda x: x["total_score"], reverse=True)

    print("\n" + "=" * 72)
    print(f"  Suspicion ranking — {event.get('title', '?')}")
    print("=" * 72)

    for i, r in enumerate(results, 1):
        flag = "🔴" if r["total_score"] >= 70 else (
            "🟡" if r["total_score"] >= 40 else "🟢")
        print(f"\n  {flag}  #{i}  {r['verdict']}  "
              f"Score: {r['total_score']}/100")
        print(f"      Address:   {r['address']}")
        print(f"      Trader:    {r['pseudonym']}")
        print(f"      Total bet: ${r['total_usdc']:,.0f}  "
              f"({r['trade_count']} trades)")
        print(f"      Direction: {fmt_dominant_outcome(r['outcomes'])}")
        print(f"      On-chain:  nonce={r['nonce']}  "
              f"balance={r['balance_matic']:,.2f} MATIC")
        print(f"      Detail:    fresh={r['fresh_score']} "
              f"size={r['size_score']} ratio={r['ratio_score']}")

    # ---- Step 7: HIGH SUSPICION highlight ----
    high = [r for r in results if r["total_score"] >= 70]
    if high:
        print("\n" + "=" * 72)
        print(f"  {len(high)} HIGH SUSPICION wallet(s) found on this event:")
        print("=" * 72)
        for r in high:
            print(f"     - {r['address']}  ({r['pseudonym']})")
            print(f"       Betting {fmt_dominant_outcome(r['outcomes'])}, "
                  f"amount ${r['total_usdc']:,.0f}")

    print("\n" + "=" * 72)
    print(f"  Done! Analyzed {len(results)} wallets")
    print("=" * 72)


if __name__ == "__main__":
    main()
