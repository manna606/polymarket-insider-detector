# Polymarket Insider Detector — Deployment Plan

> One-page deployment plan · Forward-ready

---

## 1. Current State

| Item | Status |
|---|---|
| Code | Ready (`insider_demo.py`, `live_demo.py`, etc.) |
| Dependency | Only `requests` (lightweight) |
| Data source | Polygon public RPC + Polymarket API |
| Deployment | **Not deployed yet** (local dev environment) |

---

## 2. Target Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Cloud Scheduler │────▶│  Dockerized  │────▶│  Polygon RPC    │
│  (cron / Event   │     │  Python      │     │  + Polymarket   │
│   Bridge)        │     │  Container   │     │  API            │
└─────────────────┘     └──────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  Logs /      │
                        │  Alerts      │
                        └──────────────┘
```

---

## 3. Deployment Options

| Cloud | Service | Est. Cost | Best For |
|---|---|---|---|
| **AWS** | ECS Fargate + EventBridge | ~$30–60/mo | Full control, easy cron |
| **GCP** | Cloud Run + Cloud Scheduler | ~$10–40/mo | Serverless, pay-per-run |
| **Alibaba Cloud** | Function Compute | ~¥50–150/mo | Domestic access |

**Recommendation:** GCP Cloud Run
- Reason: Stateless script, pay-per-execution, lowest overhead for PoC.

---

## 4. Implementation Steps

| Step | Task | Time |
|---|---|---|
| 1 | Add `Dockerfile` + `docker-compose.yml` | 2 hrs |
| 2 | Replace hardcoded wallets with Polymarket CLOB API feed | 4 hrs |
| 3 | Swap public RPC → Alchemy/QuickNode (prod node) | 1 hr |
| 4 | Add structured logging (`json`) + error alerting | 3 hrs |
| 5 | Write CI/CD (GitHub Actions → Cloud Run deploy) | 3 hrs |
| 6 | Schedule: every 15 min (live) or daily 08:00 UTC (batch) | 1 hr |

**Total ETA: 1–1.5 days (one engineer)**

---

## 5. Monitoring & Alerting

| What | Tool | Alert Trigger |
|---|---|---|
| Script crashes | Cloud Logging + PagerDuty/Slack | Non-zero exit code |
| RPC rate limit | Metric filter | > 5 errors / hour |
| No new data | Scheduler dead-man switch | Job missing for > 30 min |

---

## 6. Open Decisions

1. **Frequency:** Real-time (every 15 min) or daily batch?
2. **Output:** Raw JSON log, Slack alert, or dashboard (Grafana)?
3. **Priority:** Deploy first, or finish backtest validation first?

---

## 7. One-Sentence Summary

> "Code is ready. Moving from local to cloud is a standard DevOps task — **1 day of work** once we confirm the signal is worth running."

---

*Author: Nannan · Status: Ready to execute on approval*
