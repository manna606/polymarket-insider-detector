"""
Polymarket Insider Detector — Demo v0.1
============================================================
Purpose: demonstrate how to identify "insider-suspicious wallets"
         on Polymarket using on-chain data.

Core idea (inspired by pselamy/polymarket-insider-tracker):
    Insider traders tend to use fresh wallets and place large trades
    to hide their identity. We query Polygon on-chain history + balance
    and assign each wallet an "Insider Suspicion Score".

Usage:
    pip install requests
    python3 insider_demo.py

Expected runtime: ~10 seconds (network-dependent)
Dependencies: requests (only dependency)
============================================================
"""

import requests
import time
from typing import Optional, Dict


# ============================================================
# 1) Config
# ============================================================

# Polygon public RPC (free, no registration needed)
# Production tip: switch to Alchemy / QuickNode paid endpoints
#   for better stability and looser rate limits.
# Fallback endpoints if the main one fails:
#   "https://1rpc.io/matic"
#   "https://polygon.llamarpc.com"
POLYGON_RPC = "https://polygon.drpc.org"

# Core insider-detection thresholds (hyperparameters that can be
# optimized via historical backtests in the future)
FRESH_WALLET_NONCE_THRESHOLD = 10   # < 10 on-chain txs = "fresh wallet"
LARGE_TRADE_USDC = 1000              # single trade > $1000 = "large"


# ============================================================
# 2) Test sample: a few real wallet addresses
# ------------------------------------------------------------
# In production these should come from the Polymarket CLOB API
# in real time. Here we use a "control group" + "experiment group"
# to demonstrate the scoring logic:
#   - Vitalik wallet: very active on-chain, should score very low
#   - Zero address: system address, score depends on balance
#   - Feel free to replace with real suspicious addresses from Polymarket
# ============================================================

SAMPLE_WALLETS = [
    {
        "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        "trade_size_usdc": 500,
        "market": "Will ETH hit $5000 by 2026?",
        "note": "Vitalik public wallet (baseline control)",
    },
    {
        "address": "0x0000000000000000000000000000000000000001",
        "trade_size_usdc": 50000,
        "market": "Will Trump pardon someone in Q1?",
        "note": "Near-blank address (high-suspicion simulation)",
    },
    {
        "address": "0xF977814e90dA44bFA03b6295A0616a897441aceC",
        "trade_size_usdc": 25000,
        "market": "Will Fed cut rates in December?",
        "note": "Binance 8 hot wallet (typical funding source)",
    },
    # Add real suspicious addresses you scraped from Polymarket below
]


# ============================================================
# 3) On-chain data queries via Polygon RPC
# ============================================================

def rpc_call(method: str, params: list) -> Optional[dict]:
    """Generic JSON-RPC call wrapper."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        resp = requests.post(POLYGON_RPC, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"   RPC error ({method}): {e}")
        return None


def get_nonce(address: str) -> Optional[int]:
    """
    Query total transaction count (nonce) of a wallet.
    nonce = 0  -> this address has never initiated a transaction (brand new)
    The smaller the nonce, the newer the wallet, the more suspicious.
    """
    result = rpc_call("eth_getTransactionCount", [address, "latest"])
    if not result or "result" not in result:
        return None
    return int(result["result"], 16)


def get_balance_matic(address: str) -> Optional[float]:
    """Query current MATIC balance (converted to MATIC units)."""
    result = rpc_call("eth_getBalance", [address, "latest"])
    if not result or "result" not in result:
        return None
    wei = int(result["result"], 16)
    return wei / 1e18  # 1 MATIC = 1e18 wei


# ============================================================
# 4) Insider suspicion scoring model
# ------------------------------------------------------------
# This is a heuristic demo score, weighted across three dimensions:
#   1) Fresh Score:   wallet newness          (0~40 pts)
#   2) Size Score:    absolute trade size     (0~30 pts)
#   3) Ratio Score:   trade-to-balance ratio  (0~30 pts)
# Higher total = more suspicious (max 100)
# ============================================================

def calculate_suspicion_score(
    nonce: int, balance: float, trade_size: float
) -> Dict:
    # 1) Fresh wallet score
    if nonce <= 5:
        fresh = 40
    elif nonce <= 20:
        fresh = 25
    elif nonce <= 100:
        fresh = 10
    else:
        fresh = 0

    # 2) Trade size score
    if trade_size >= 50000:
        size = 30
    elif trade_size >= 10000:
        size = 20
    elif trade_size >= 1000:
        size = 10
    else:
        size = 0

    # 3) Trade-to-balance ratio score
    # All-in bet -> extreme confidence -> highly suspicious
    if balance > 0:
        ratio = trade_size / max(balance, 0.01)
        if ratio > 100:
            ratio_score = 30
        elif ratio > 10:
            ratio_score = 15
        else:
            ratio_score = 0
    else:
        ratio_score = 30  # near-zero balance but large trade

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
        return "HIGH SUSPICION"
    elif score >= 40:
        return "MEDIUM SUSPICION"
    elif score >= 20:
        return "LOW SUSPICION"
    else:
        return "CLEAN"


# ============================================================
# 5) Single-wallet analysis pipeline
# ============================================================

def analyze_wallet(wallet_info: dict) -> Optional[dict]:
    addr = wallet_info["address"]
    trade_size = wallet_info["trade_size_usdc"]

    print(f"\nAnalyzing address: {addr[:10]}...{addr[-6:]}")
    print(f"   Market:   {wallet_info['market']}")
    print(f"   Trade:    ${trade_size:,.0f}")
    print(f"   Note:     {wallet_info['note']}")

    nonce = get_nonce(addr)
    balance = get_balance_matic(addr)

    if nonce is None or balance is None:
        print("   On-chain data query failed, skipping")
        return None

    print(f"   On-chain nonce: {nonce}")
    print(f"   MATIC balance:  {balance:,.4f}")

    score = calculate_suspicion_score(nonce, balance, trade_size)
    print(f"   Suspicion score: {score['total_score']}/100  {score['verdict']}")

    return {
        "address": addr,
        "market": wallet_info["market"],
        "trade_size": trade_size,
        "nonce": nonce,
        "balance_matic": balance,
        **score,
    }


# ============================================================
# 6) Main
# ============================================================

def main():
    print("=" * 60)
    print("  Polymarket Insider Detector — Demo v0.1")
    print("  (Reference: pselamy/polymarket-insider-tracker)")
    print("=" * 60)

    results = []
    for wallet in SAMPLE_WALLETS:
        result = analyze_wallet(wallet)
        if result:
            results.append(result)
        time.sleep(0.3)  # avoid RPC rate limiting

    # Sort by suspicion (high -> low)
    print("\n" + "=" * 60)
    print("  Final ranking report (high -> low)")
    print("=" * 60)

    results.sort(key=lambda x: x["total_score"], reverse=True)
    for r in results:
        print(f"\n  {r['verdict']}   Score: {r['total_score']}/100")
        print(f"  Address:  {r['address']}")
        print(f"  Market:   {r['market']}")
        print(f"  Trade:    ${r['trade_size']:,.0f}")
        print(f"  Nonce:    {r['nonce']}   "
              f"Balance: {r['balance_matic']:,.4f} MATIC")
        print(f"  Detail:   fresh={r['fresh_score']}  "
              f"size={r['size_score']}  ratio={r['ratio_score']}")

    print("\n" + "=" * 60)
    print(f"  Done! Analyzed {len(results)} wallets.")
    print("=" * 60)
    print("\nNext steps:")
    print("   1) Integrate Polymarket CLOB API to pull recent large-order wallets")
    print("   2) Add funding-source tracing: track where a wallet's funds came from")
    print("   3) Add wallet age: use Polygonscan API to check first activity time")
    print("   4) Add DBSCAN clustering: find sniper wallet clusters")
    print("   5) Historical backtest: does this score actually predict price moves?")


if __name__ == "__main__":
    main()
