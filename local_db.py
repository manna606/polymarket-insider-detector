"""
Local Database Adapter
============================================================
Automatically chooses PostgreSQL (Railway) or SQLite (local).
For beginners: SQLite works out of the box, zero installation.
"""

import os
import re
import sqlite3
from datetime import datetime, date
from typing import Optional

try:
    import psycopg2
    from psycopg2.extras import execute_values
    HAS_PG = True
except ImportError:
    HAS_PG = False

SQLITE_PATH = os.environ.get("SQLITE_PATH", "polymarket_data.db")


def get_db_conn():
    """Return PostgreSQL conn if DATABASE_URL set, else SQLite."""
    url = os.environ.get("DATABASE_URL")
    if url and HAS_PG:
        conn = psycopg2.connect(url)
        return conn

    # Fallback: local SQLite file (zero setup)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    _init_sqlite(conn)
    return conn


def is_sqlite(conn) -> bool:
    return isinstance(conn, sqlite3.Connection)


def sql_for_conn(sql: str, conn) -> str:
    """Replace positional %%s with ? for SQLite compatibility."""
    if isinstance(conn, sqlite3.Connection):
        return sql.replace('%s', '?')
    return sql


def _init_sqlite(conn: sqlite3.Connection):
    """Create tables for SQLite (runs only once)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS markets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            external_id TEXT NOT NULL,
            slug TEXT,
            question TEXT NOT NULL,
            category TEXT,
            outcomes TEXT,
            outcome_prices TEXT,
            volume REAL DEFAULT 0,
            liquidity REAL DEFAULT 0,
            active INTEGER DEFAULT 1,
            closed INTEGER DEFAULT 0,
            resolution TEXT,
            end_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform, external_id)
        );

        CREATE INDEX IF NOT EXISTS idx_markets_platform ON markets(platform);
        CREATE INDEX IF NOT EXISTS idx_markets_active ON markets(active, closed);

        CREATE TABLE IF NOT EXISTS price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id INTEGER NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
            snapshot_date TEXT NOT NULL,
            outcome_prices TEXT NOT NULL,
            volume REAL DEFAULT 0,
            open_interest REAL DEFAULT 0,
            spread REAL DEFAULT 0,
            best_bid REAL DEFAULT 0,
            best_ask REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(market_id, snapshot_date)
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_market ON price_snapshots(market_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_date ON price_snapshots(snapshot_date);

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            market_id INTEGER NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
            external_trade_id TEXT,
            wallet TEXT,
            pseudonym TEXT,
            side TEXT,
            outcome TEXT,
            size REAL,
            price REAL,
            usdc_amount REAL,
            timestamp TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform, external_trade_id)
        );

        CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_id);
        CREATE INDEX IF NOT EXISTS idx_trades_wallet ON trades(wallet);
        CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);

        CREATE TABLE IF NOT EXISTS alpha_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_date TEXT NOT NULL,
            test_name TEXT NOT NULL,
            market_id INTEGER REFERENCES markets(id),
            description TEXT,
            metric_value REAL,
            sample_size INTEGER DEFAULT 0,
            p_value REAL,
            is_significant INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_alpha_date ON alpha_results(test_date);

        CREATE TABLE IF NOT EXISTS arbitrage_opps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            event_name TEXT NOT NULL,
            poly_market_id INTEGER REFERENCES markets(id),
            kalshi_market_id INTEGER REFERENCES markets(id),
            poly_price_yes REAL,
            kalshi_price_yes REAL,
            spread REAL,
            spread_pct REAL,
            potential_profit REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_arb_date ON arbitrage_opps(snapshot_date);
        """
    )
    conn.commit()
