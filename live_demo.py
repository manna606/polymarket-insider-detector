"""
Polymarket Insider Detector — Demo v0.2 (LIVE)
============================================================
v0.2 upgrade: pull real recent large orders from Polymarket
              -> on-chain analysis -> ranked output

Improvements over v0.1:
    - No more hardcoded addresses; fetches real trades in real time
    - Added exchange / system address whitelist (reduces false positives)
    - Deduplicates multiple trades from the same wallet (keeps largest)
    - Output includes market name, direction (BUY/SELL), pseudonym, etc.

Usage:
    python3 live_demo.py

Dependencies: requests (only dependency)
============================================================
"""

import requests
import time
from typing import Optional, Dict, List


# ============================================================
# 1) Config
# ============================================================

# Polymarket public data-api (no auth required)
POLYMARKET_DATA_API = "https://data-api.polymarket.com/trades"

# Polygon public RPC (no auth required)
POLYGON_RPC = "https://polygon.drpc.org"

# Fetch parameters
TRADES_TO_FETCH = 500          # how many recent trades to pull at once
MIN_TRADE_USDC = 500           # only track large orders >= $500 (tunable)
MAX_WALLETS_TO_ANALYZE = 15    # max wallets to analyze (limits RPC calls)

# Scoring thresholds
FRESH_NONCE_THRESHOLD = 10
LARGE_USDC_THRESHOLD = 1000


# ============================================================
# 2) Known address whitelist
# ------------------------------------------------------------
# These addresses should NOT be flagged as insiders:
#   - Exchange hot wallets (high nonce but not individual traders)
#   - System / burn addresses (no one controls them)
# In production this should be maintained as a database, updated continuously
# ============================================================

KNOWN_ADDRESSES_LOWER = {
    "0x0000000000000000000000000000000000000000": "Zero Address",
    "0x0000000000000000000000000000000000000001": "Burn Address (1)",
    "0x000000000000000000000000000000000000dead": "Burn Address (dead)",
    # Major centralized exchanges
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance 8",
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
    "0xa910f92acdaf488fa6ef02174fb86208ad7722ba": "OKX",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
}


# ============================================================
# 3) Data ingestion layer (Polymarket)
# ============================================================

def fetch_recent_trades(limit: int = 500) -> List[dict]:
    """Pull recent trades from Polymarket (public endpoint, no key needed)."""
    print(f"Fetching recent {limit} trades from Polymarket...")
    try:
        resp = requests.get(POLYMARKET_DATA_API,
                            params={"limit": limit},
                            timeout=30)
        resp.raise_for_status()
        trades = resp.json()
        print(f"   Got {len(trades)} trades")
        return trades
    except Exception as e:
        print(f"   Fetch failed: {e}")
        return []


def filter_and_format_large_trades(
    trades: List[dict], min_usdc: float = 500
) -> List[dict]:
    """
    Filter + format large trades.
    USDC amount = size (shares) * price (0~1)
    """
    formatted = []
    for t in trades:
        try:
            size = float(t.get("size", 0))
            price = float(t.get("price", 0))
            usdc = size * price
            if usdc < min_usdc:
                continue
            formatted.append({
                "address": t["proxyWallet"],
                "trade_size_usdc": usdc,
                "market": t.get("title", "Unknown"),
                "side": t.get("side", "?"),
                "outcome": t.get("outcome", "?"),
                "pseudonym": (t.get("pseudonym") or t.get("name")
                              or "anon"),
                "timestamp": t.get("timestamp", 0),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return formatted


def deduplicate_by_wallet(trades: List[dict]) -> List[dict]:
    """
    If the same wallet appears multiple times, keep only the largest trade.
    Prevents one wallet from dominating the analysis quota.
    """
    by_wallet: Dict[str, dict] = {}
    for t in trades:
        addr = t["address"].lower()
        if (addr not in by_wallet
                or t["trade_size_usdc"] > by_wallet[addr]["trade_size_usdc"]):
            by_wallet[addr] = t
    return list(by_wallet.values())


def exclude_known_addresses(trades: List[dict]) -> List[dict]:
    """Remove known exchange / system addresses (whitelist)."""
    return [t for t in trades
            if t["address"].lower() not in KNOWN_ADDRESSES_LOWER]


# ============================================================
# 4) On-chain data queries (Polygon RPC)
# ============================================================

def rpc_call(method: str, params: list) -> Optional[dict]:
    payload = {"jsonrpc": "2.0", "method": method,
               "params": params, "id": 1}
    try:
        resp = requests.post(POLYGON_RPC, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"   RPC error: {e}")
        return None


def get_nonce(address: str) -> Optional[int]:
    r = rpc_call("eth_getTransactionCount", [address, "latest"])
    if not r or "result" not in r:
        return None
    return int(r["result"], 16)


def get_balance_matic(address: str) -> Optional[float]:
    r = rpc_call("eth_getBalance", [address, "latest"])
    if not r or "result" not in r:
        return None
    return int(r["result"], 16) / 1e18


# ============================================================
# 5) Suspicion scoring (same as v0.1)
# ============================================================

def calculate_suspicion_score(
    nonce: int, balance: float, trade_size: float
) -> Dict:
    if nonce <= 5:
        fresh = 40
    elif nonce <= 20:
        fresh = 25
    elif nonce <= 100:
        fresh = 10
    else:
        fresh = 0

    if trade_size >= 50000:
        size = 30
    elif trade_size >= 10000:
        size = 20
    elif trade_size >= 1000:
        size = 10
    else:
        size = 0

    if balance > 0:
        ratio = trade_size / max(balance, 0.01)
        if ratio > 100:
            ratio_score = 30
        elif ratio > 10:
            ratio_score = 15
        else:
            ratio_score = 0
    else:
        ratio_score = 30

    total = fresh + size + ratio_score
    return {
        "fresh_score": fresh,
        "size_score": size,
        "ratio_score": ratio_score,
        "total_score": total,
        "verdict": _verdict(total),
    }


def _verdict(score: int) -> str:
    if score >= 70:
        return "HIGH"
    elif score >= 40:
        return "MEDIUM"
    elif score >= 20:
        return "LOW"
    return "CLEAN"


# ============================================================
# 6) Single-wallet analysis
# ============================================================

def analyze_wallet(t: dict) -> Optional[dict]:
    addr = t["address"]
    print(f"  {addr[:10]}...{addr[-6:]}  "
          f"({t['pseudonym'][:18]:<18}) "
          f"${t['trade_size_usdc']:>8,.0f}  "
          f"[{t['side']:<4} {t['outcome'][:15]:<15}]  "
          f"{t['market'][:40]}")

    nonce = get_nonce(addr)
    balance = get_balance_matic(addr)
    if nonce is None or balance is None:
        return None

    score = calculate_suspicion_score(nonce, balance, t["trade_size_usdc"])
    print(f"      -> nonce={nonce:<6} balance={balance:>10,.2f} MATIC  "
          f"score={score['total_score']:>3}/100  {score['verdict']}")

    return {**t, "nonce": nonce, "balance_matic": balance, **score}


# ============================================================
# 7) Main
# ============================================================

def main():
    print("=" * 70)
    print("  Polymarket Insider Detector — Demo v0.2 (LIVE)")
    print("=" * 70)

    # ----- Step 1: Fetch recent trades in real time -----
    raw = fetch_recent_trades(TRADES_TO_FETCH)
    if not raw:
        print("No data received, check network")
        return

    # ----- Step 2: Filter large trades -----
    big = filter_and_format_large_trades(raw, MIN_TRADE_USDC)
    print(f"   Large trades (>= ${MIN_TRADE_USDC}): {len(big)}")

    if len(big) == 0:
        print(f"No large trades found in the last {TRADES_TO_FETCH} trades "
              f"(>= ${MIN_TRADE_USDC}). Try lowering MIN_TRADE_USDC.")
        return

    # ----- Step 3: Deduplicate + whitelist -----
    unique = deduplicate_by_wallet(big)
    print(f"   Unique wallets after dedup: {len(unique)}")

    candidates = exclude_known_addresses(unique)
    print(f"   Candidates after whitelist: {len(candidates)}")

    candidates.sort(key=lambda x: x["trade_size_usdc"], reverse=True)
    candidates = candidates[:MAX_WALLETS_TO_ANALYZE]
    print(f"   Top {len(candidates)} selected for on-chain analysis\n")

    # ----- Step 4: On-chain analysis per wallet -----
    print("On-chain analysis running...")
    results = []
    for c in candidates:
        r = analyze_wallet(c)
        if r:
            results.append(r)
        time.sleep(0.3)  # avoid RPC rate limiting

    if not results:
        print("No wallets were successfully analyzed")
        return

    # ----- Step 5: Output report -----
    results.sort(key=lambda x: x["total_score"], reverse=True)

    print("\n" + "=" * 70)
    print("  Suspicion ranking (high -> low)")
    print("=" * 70)

    for i, r in enumerate(results, 1):
        print(f"\n  #{i}  {r['verdict']}  Score: {r['total_score']}/100")
        print(f"      Address:  {r['address']}")
        print(f"      Trader:   {r['pseudonym']}")
        print(f"      Market:   {r['market']}")
        print(f"      Position: {r['side']} {r['outcome']}  "
              f"@ ${r['trade_size_usdc']:,.0f}")
        print(f"      On-chain: nonce={r['nonce']}  "
              f"balance={r['balance_matic']:,.2f} MATIC")
        print(f"      Detail:   fresh={r['fresh_score']} "
              f"size={r['size_score']} ratio={r['ratio_score']}")

    # ----- Step 6: HIGH SUSPICION alert -----
    high = [r for r in results if r["total_score"] >= 70]
    if high:
        print("\n" + "=" * 70)
        print(f"  {len(high)} HIGH SUSPICION wallet(s) flagged:")
        print("=" * 70)
        for r in high:
            print(f"     - {r['address']}  ({r['pseudonym']})")
            print(f"       Betting {r['side']} '{r['outcome']}' "
                  f"on '{r['market'][:50]}'")
            print(f"       Amount ${r['trade_size_usdc']:,.0f}, "
                  f"score={r['total_score']}/100")

    print("\n" + "=" * 70)
    print(f"  Done! Analyzed {len(results)} unique wallets")
    print("=" * 70)


if __name__ == "__main__":
    main()
