-- Polymarket + Kalshi Data Pipeline Schema
-- Run: psql $DATABASE_URL -f schema.sql

-- ============================================================
-- 1) Markets master table
-- ============================================================
CREATE TABLE IF NOT EXISTS markets (
    id              SERIAL PRIMARY KEY,
    platform        VARCHAR(20) NOT NULL,        -- 'polymarket' or 'kalshi'
    external_id     VARCHAR(100) NOT NULL,       -- conditionId or event_id
    slug            VARCHAR(255),
    question        TEXT NOT NULL,
    category        VARCHAR(100),
    outcomes        JSONB,                       -- ["Yes","No"] or ["Up","Down"]
    outcome_prices  JSONB,                       -- current prices per outcome
    volume          NUMERIC(20, 4) DEFAULT 0,
    liquidity       NUMERIC(20, 4) DEFAULT 0,
    active          BOOLEAN DEFAULT TRUE,
    closed          BOOLEAN DEFAULT FALSE,
    resolution      VARCHAR(100),                -- winning outcome if resolved
    end_date        TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(platform, external_id)
);

CREATE INDEX IF NOT EXISTS idx_markets_platform ON markets(platform);
CREATE INDEX IF NOT EXISTS idx_markets_active ON markets(active, closed);
CREATE INDEX IF NOT EXISTS idx_markets_category ON markets(category);

-- ============================================================
-- 2) Daily price snapshots
-- ============================================================
CREATE TABLE IF NOT EXISTS price_snapshots (
    id              SERIAL PRIMARY KEY,
    market_id       INTEGER NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    snapshot_date   DATE NOT NULL,
    outcome_prices  JSONB NOT NULL,              -- {"Yes": 0.65, "No": 0.35}
    volume          NUMERIC(20, 4) DEFAULT 0,
    open_interest   NUMERIC(20, 4) DEFAULT 0,
    spread          NUMERIC(10, 4) DEFAULT 0,    -- best_ask - best_bid
    best_bid        NUMERIC(10, 4) DEFAULT 0,
    best_ask        NUMERIC(10, 4) DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(market_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_market ON price_snapshots(market_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON price_snapshots(snapshot_date);

-- ============================================================
-- 3) Whale trades (Polymarket only — Kalshi requires API key)
-- ============================================================
CREATE TABLE IF NOT EXISTS trades (
    id              SERIAL PRIMARY KEY,
    platform        VARCHAR(20) NOT NULL,
    market_id       INTEGER NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    external_trade_id VARCHAR(100),
    wallet          VARCHAR(100),                -- proxyWallet or account_id
    pseudonym       VARCHAR(100),
    side            VARCHAR(10),                 -- BUY / SELL
    outcome         VARCHAR(100),
    size            NUMERIC(20, 8),
    price           NUMERIC(20, 8),
    usdc_amount     NUMERIC(20, 4),
    timestamp       TIMESTAMP NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(platform, external_trade_id)
);

CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_id);
CREATE INDEX IF NOT EXISTS idx_trades_wallet ON trades(wallet);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);

-- ============================================================
-- 4) Alpha validation results (computed daily)
-- ============================================================
CREATE TABLE IF NOT EXISTS alpha_results (
    id              SERIAL PRIMARY KEY,
    test_date       DATE NOT NULL,
    test_name       VARCHAR(100) NOT NULL,       -- e.g. 'calibration_70pct'
    market_id       INTEGER REFERENCES markets(id),
    description     TEXT,
    metric_value    NUMERIC(20, 8),
    sample_size     INTEGER DEFAULT 0,
    p_value         NUMERIC(10, 6),
    is_significant  BOOLEAN DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alpha_date ON alpha_results(test_date);

-- ============================================================
-- 5) Cross-market arbitrage opportunities
-- ============================================================
CREATE TABLE IF NOT EXISTS arbitrage_opps (
    id              SERIAL PRIMARY KEY,
    snapshot_date   DATE NOT NULL,
    event_name      VARCHAR(255) NOT NULL,       -- e.g. "Trump wins 2024"
    poly_market_id  INTEGER REFERENCES markets(id),
    kalshi_market_id INTEGER REFERENCES markets(id),
    poly_price_yes  NUMERIC(10, 4),
    kalshi_price_yes NUMERIC(10, 4),
    spread          NUMERIC(10, 4),              -- absolute difference
    spread_pct      NUMERIC(10, 4),              -- spread / avg_price
    potential_profit NUMERIC(10, 4),             -- after fees (rough)
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arb_date ON arbitrage_opps(snapshot_date);
