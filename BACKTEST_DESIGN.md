# Polymarket Insider Signal — Backtest Design (v0.1)

> One-page statistical design for validating whether the v0.4 behavioral
> suspicion score actually predicts winners.
> Author: Nannan · For: Henry · Status: pre-implementation draft

---

## 1. The Question

Does the v0.4 behavioral suspicion score have alpha — i.e. do
HIGH-suspicion wallets win more often than chance on Polymarket events?

---

## 2. Hypotheses

| | Null (H₀) | Alternative (H₁) |
|---|---|---|
| **H₀** | HIGH-suspicion wallets win at the same rate as the baseline. The score is noise. |
| **H₁** | HIGH-suspicion wallets win at a rate strictly above baseline. The score has alpha. |

One-sided test (we do not care about the case "HIGH wallets are
systematically wrong" — that is still alpha, just inverted, but for v0.1
we test the natural direction).

---

## 3. Data Requirements

- 30–50 already-resolved Polymarket events (closed=True, has UMA resolution)
- Event mix: NOT all consensus (need contested 50/50 events for power)
- For each event: list of all trades (size, price, side, outcome, wallet, timestamp)
- For each event: final winning outcome

**Source preference:**
1. QuantSignals internal closed-event DB (preferred — pre-validated)
2. `gamma-api.polymarket.com/events?closed=true&limit=...` (fallback)

---

## 4. Test Procedure

1. For each event Eᵢ, run v0.4 -> get list of HIGH wallets (score >= 60).
2. For each HIGH wallet w in event Eᵢ:
   - Compute `bet_PnL(w, Eᵢ)`: did their dominant outcome win?
   - Score = +1 if won, 0 otherwise (or use $-weighted PnL).
3. Compute `hit_rate_HIGH = mean(bet_PnL across all HIGH bets)`.
4. **Baseline**: same calculation but on randomly sampled wallets of
   similar bet size from the same events. Repeat baseline draw 1,000 times
   to get null distribution.
5. **Test statistic**: `t = (hit_rate_HIGH - mean(baseline)) / sd(baseline)`.

---

## 5. Significance Threshold & Multiple Testing

- Per-event significance: `p < 0.05` (one-sided).
- We will also try alternate score thresholds (HIGH >= 60, MEDIUM >= 30,
  custom >= 40, etc.) and feature subsets — that is **multiple hypothesis
  testing**.
- Apply **Benjamini-Hochberg (FDR)** at q = 0.10 across all tested
  configurations. Report only configurations that survive correction.

**Why this matters:** Without FDR, trying 20 thresholds means ~1
will look "significant" at p < 0.05 by pure luck. UCB-trained answer is
to control discovery rate, not naive p-value.

---

## 6. Sample Size & Power

Rough power calculation (assuming binary win/loss):

- Baseline win rate ~ 50% (Polymarket prices roughly Bayesian by close).
- Detectable effect: HIGH wallets at 60% win rate (10 pp lift).
- Required N for 80% power, alpha = 0.05: ~200 HIGH-bet observations.
- With ~5 HIGH wallets per event x 40 events = 200. **This sets our
  minimum event count.**

---

## 7. Decision Rule

| Outcome | Action |
|---|---|
| HIGH wallet hit rate > baseline, p < 0.05 after FDR | Signal has alpha. Greenlight live monitor build. |
| HIGH wallet hit rate ~ baseline (no significance) | Score has no alpha. Reformulate features (e.g. add timing, accuracy). |
| HIGH wallet hit rate < baseline, p < 0.05 (signal **inverted**) | Interesting — HIGH wallets are systematically wrong. Check for reverse-arbitrage opportunity, but also consider data leakage. |

---

## 8. Known Risks

1. **Survivorship in event selection**: only resolved events are tested.
   Bias-corrected by sampling resolved events uniformly across time
   periods, not just recent.
2. **Look-ahead bias**: when computing v0.4 features for a closed event,
   make sure features only use data **available before each user's bet
   timestamp** (e.g. account_age relative to that bet, not relative to
   today).
3. **500-trade truncation** (already known bug): until fixed, the
   `total_trades` and `diversification` features are degraded for power
   users. Report results both with the bug and with a paginated re-pull.
4. **Polymarket pricing efficiency**: if prices already reflect insider
   info quickly, even a correctly-detected insider may not show profit
   because they bought at the new price.

---

## 9. Deliverables

- [ ] `backtest.py`: runs the procedure on a list of resolved events
- [ ] `backtest_report.md`: results table (config x hit rate x p-value x FDR-adj p)
- [ ] One-pager for Henry summarizing the decision

---

## 10. Out of Scope (for v0.1 backtest)

- Cross-event clustering (DBSCAN sniper detection)
- News-timestamp alignment for "before/after catalyst" timing feature
- Funding-source tracing (proxy wallet limitation makes this hard anyway)
- Live monitoring infrastructure

---

*This design is pre-registered. Any deviation during implementation
should be documented and justified, to maintain statistical credibility.*
