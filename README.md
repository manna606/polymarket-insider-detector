# Polymarket Insider Detector — Demo v0.1

> First Polymarket insider-detection demo for junior researchers
> Goal: run in 3 minutes → understand the core logic → demo it to Henry

---

## What does this demo do?

**Core idea** (based on [pselamy/polymarket-insider-tracker](https://github.com/pselamy/polymarket-insider-tracker)):

> Instead of predicting event outcomes, we identify wallets that likely possess insider information via on-chain behavior.

Specifically, the script does three things:

1. Takes a list of Polymarket wallet addresses as input
2. Queries on-chain transaction count (nonce) and MATIC balance via Polygon public RPC
3. Scores each wallet with a simple 0–100 insider suspicion score

---

## How to run

```bash
# 1) Install dependencies (only requests)
pip install -r requirements.txt

# 2) Run
python3 insider_demo.py
```

Expected output: on-chain profile + suspicion ranking for each wallet.

---

## Scoring model

Total = `Fresh Score (0~40)` + `Size Score (0~30)` + `Ratio Score (0~30)`

| Dimension | Meaning | Why it is an alpha signal |
|---|---|---|
| **Fresh Score** | The fewer on-chain transactions (the newer the wallet), the higher the score | Insider traders tend to use fresh wallets to hide identity |
| **Size Score** | The larger the single trade, the higher the score | Large order = entering regardless of cost = high-conviction info |
| **Ratio Score** | The larger the trade relative to balance, the higher the score | All-in bet = extreme confidence = suspicious |

Thresholds:
- >= 70  -> HIGH SUSPICION
- 40~69  -> MEDIUM SUSPICION
- 20~39  -> LOW SUSPICION
- < 20   -> CLEAN

---

## Key observations on first run (worth discussing with Henry)

```
HIGH SUSPICION   Score: 85/100   nonce=0  trade=$50k
MEDIUM SUSPICION Score: 50/100   nonce=746 trade=$25k
MEDIUM SUSPICION Score: 40/100   nonce=1  (Vitalik!)
```

**Unexpected finding**: Vitalik's wallet has a nonce of only 1 on **Polygon**.
This exposes a **critical flaw** in v0.1:

> Looking at Polygon nonce alone misclassifies "established Ethereum users but Polygon newcomers" as fresh wallets.

This is a classic feature-proxy validity problem a UCB statistics background should flag.
True fresh-wallet detection should combine multi-chain history, first-activity time, funding source, etc.

This is exactly what v0.2 aims to solve.

---

## Next steps (v0.2 roadmap)

Prioritized; each is an independent small project you can finish alone:

- [ ] **Integrate Polymarket CLOB API**: pull recent large-order wallets in real time, replace hardcoded addresses
- [ ] **Multi-dimensional freshness metrics**: use Polygonscan API to check "first activity time" combined with nonce
- [ ] **Funding-source tracing**: trace which address/exchange a wallet's funds came from (funding chain)
- [ ] **DBSCAN clustering**: identify "sniper wallet clusters" (multiple wallets entering collectively within a short window)
- [ ] **Historical backtest**: for each flagged suspicious wallet, track contract price movement in the following 24h
  - This is the **most critical step** to validate whether the signal has alpha
  - Use event study + multiple testing correction (FDR / Bonferroni)

---

## One-sentence summary for Henry (copy-paste ready)

> "I have v0.1's minimal demo running: it can score any Polymarket wallet for insider suspicion.
> In the test sample I found that Polygon nonce alone is not robust (Vitalik was misclassified as medium).
> Next I want to integrate CLOB real-time data and run historical backtests to validate the score's predictive power."

This one sentence shows:
- Strong execution (already running)
- Statistical intuition (found model flaw)
- Clear next step (validate alpha rather than stacking features)

---

## File structure

```
polymarket_demo/
├── insider_demo.py     # main script (~200 lines, commented)
├── requirements.txt    # single dependency: requests
└── README.md           # this file
```

---

## Blockchain concepts crash course (90 seconds)

| Concept | Explanation |
|---|---|
| **Polygon** | An Ethereum-compatible low-fee chain; Polymarket runs on it |
| **Wallet / Address** | A 42-character string starting with 0x, the unique ID of a wallet |
| **Nonce** | Total number of transactions sent by this address; +1 for each sent tx |
| **RPC** | Remote Procedure Call; an HTTP endpoint to query blockchain data |
| **MATIC** | The native token of the Polygon chain (like ETH on Ethereum) |
| **USDC** | USD stablecoin; Polymarket denominates contracts in USDC |

---

Made for QuantSignals research.
