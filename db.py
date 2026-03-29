"""SQLite helpers — schema creation, inserts, queries."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.environ.get("BUNSHEE_DB", Path(__file__).parent / "spending.db"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp           TEXT    NOT NULL,
                source              TEXT    NOT NULL,
                raw_text            TEXT,
                merchant            TEXT,
                amount              REAL,
                currency            TEXT    DEFAULT 'THB',
                category            TEXT,
                confidence          REAL,
                clarification_needed INTEGER DEFAULT 0,
                notes               TEXT
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name  TEXT    NOT NULL UNIQUE,
                amount        REAL,
                currency      TEXT    DEFAULT 'THB',
                billing_cycle TEXT,
                last_charged  TEXT,
                next_renewal  TEXT,
                status        TEXT    DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS classification_rules (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern      TEXT    NOT NULL,
                category     TEXT    NOT NULL,
                created_from TEXT    DEFAULT 'manual'
            );

            CREATE TABLE IF NOT EXISTS merchant_memory (
                merchant        TEXT    PRIMARY KEY,
                is_subscription INTEGER NOT NULL,
                category        TEXT,
                created_at      TEXT    NOT NULL
            );
        """)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def insert_transaction(
    source: str,
    raw_text: str,
    merchant: str,
    amount: float,
    currency: str,
    category: str,
    confidence: float,
    clarification_needed: bool = False,
    notes: str = None,
) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO transactions
               (timestamp, source, raw_text, merchant, amount, currency,
                category, confidence, clarification_needed, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                datetime.now().isoformat(),
                source, raw_text, merchant, amount, currency,
                category, confidence, int(clarification_needed), notes,
            ),
        )
        return cur.lastrowid


def update_transaction(
    tx_id: int,
    category: str = None,
    notes: str = None,
    clarification_needed: bool = None,
) -> None:
    parts, params = [], []
    if category is not None:
        parts.append("category = ?"); params.append(category)
    if notes is not None:
        parts.append("notes = ?"); params.append(notes)
    if clarification_needed is not None:
        parts.append("clarification_needed = ?"); params.append(int(clarification_needed))
    if not parts:
        return
    params.append(tx_id)
    with _conn() as conn:
        conn.execute(f"UPDATE transactions SET {', '.join(parts)} WHERE id = ?", params)


def get_transactions(
    limit: int = 100,
    source: str = None,
    category: str = None,
    month: str = None,
) -> list[dict]:
    q = "SELECT * FROM transactions WHERE 1=1"
    p = []
    if source:
        q += " AND source = ?"; p.append(source)
    if category:
        q += " AND category = ?"; p.append(category)
    if month:
        q += " AND timestamp LIKE ?"; p.append(f"{month}%")
    q += " ORDER BY timestamp DESC LIMIT ?"
    p.append(limit)
    with _conn() as conn:
        return [dict(r) for r in conn.execute(q, p)]


def get_monthly_summary(month: str = None) -> dict:
    if not month:
        month = datetime.now().strftime("%Y-%m")
    with _conn() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count
               FROM transactions WHERE timestamp LIKE ? AND clarification_needed=0""",
            (f"{month}%",),
        ).fetchone()
        cats = conn.execute(
            """SELECT category, COALESCE(SUM(amount),0) AS total
               FROM transactions WHERE timestamp LIKE ? AND clarification_needed=0
               GROUP BY category""",
            (f"{month}%",),
        ).fetchall()
        return {
            "month": month,
            "total": row["total"],
            "count": row["count"],
            "categories": {r["category"]: r["total"] for r in cats},
        }


def get_daily_spending(month: str = None) -> list[dict]:
    if not month:
        month = datetime.now().strftime("%Y-%m")
    with _conn() as conn:
        rows = conn.execute(
            """SELECT substr(timestamp,1,10) AS date, SUM(amount) AS total
               FROM transactions WHERE timestamp LIKE ? AND clarification_needed=0
               GROUP BY date ORDER BY date""",
            (f"{month}%",),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

def upsert_subscription(
    service_name: str,
    amount: float,
    currency: str,
    billing_cycle: str,
    last_charged: str,
    next_renewal: str,
    status: str = "active",
) -> int:
    with _conn() as conn:
        existing = conn.execute(
            "SELECT id, amount FROM subscriptions WHERE service_name = ?", (service_name,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE subscriptions
                   SET amount=?,currency=?,billing_cycle=?,last_charged=?,next_renewal=?,status=?
                   WHERE id=?""",
                (amount, currency, billing_cycle, last_charged, next_renewal, status, existing["id"]),
            )
            return existing["id"], existing["amount"]  # (id, old_amount)
        else:
            cur = conn.execute(
                """INSERT INTO subscriptions
                   (service_name,amount,currency,billing_cycle,last_charged,next_renewal,status)
                   VALUES (?,?,?,?,?,?,?)""",
                (service_name, amount, currency, billing_cycle, last_charged, next_renewal, status),
            )
            return cur.lastrowid, None


def get_subscriptions(status: str = "active") -> list[dict]:
    with _conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM subscriptions WHERE status=? ORDER BY next_renewal", (status,)
            )
        ]


def get_upcoming_renewals(days: int = 3) -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                """SELECT * FROM subscriptions
                   WHERE status='active' AND next_renewal BETWEEN ? AND ?""",
                (today, cutoff),
            )
        ]


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

def get_classification_rules() -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM classification_rules")]


def insert_classification_rule(pattern: str, category: str, created_from: str = "manual") -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO classification_rules (pattern,category,created_from) VALUES (?,?,?)",
            (pattern, category, created_from),
        )


# ---------------------------------------------------------------------------
# Merchant memory  (remembers subscription status per merchant — never ask twice)
# ---------------------------------------------------------------------------

def get_merchant_memory(merchant: str) -> dict | None:
    """Return stored knowledge about a merchant, or None if unknown."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM merchant_memory WHERE lower(merchant) = lower(?)", (merchant,)
        ).fetchone()
        return dict(row) if row else None


def set_merchant_memory(merchant: str, is_subscription: bool, category: str = None) -> None:
    """Remember whether a merchant is a subscription. Overwrites if already stored."""
    with _conn() as conn:
        conn.execute(
            """INSERT INTO merchant_memory (merchant, is_subscription, category, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(merchant) DO UPDATE SET
                   is_subscription = excluded.is_subscription,
                   category        = excluded.category,
                   created_at      = excluded.created_at""",
            (merchant, int(is_subscription), category, datetime.now().isoformat()),
        )


def get_all_merchant_memories() -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM merchant_memory ORDER BY merchant"
        )]


def get_transaction_by_id(tx_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (tx_id,)
        ).fetchone()
        return dict(row) if row else None


def get_pending_reviews(limit: int = 100) -> list[dict]:
    """Return transactions that still need user clarification."""
    with _conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                """SELECT * FROM transactions
                   WHERE clarification_needed = 1
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            )
        ]
