"""
dispatch.py — Deprecated. Use fetch.py instead.
Kept only so old references don't break.

Fetches new KTC + KBank emails via IMAP, parses them, inserts into spending.db,
and regenerates transactions.csv.

Run manually any time (or when Cowork says "dispatch"):
    python3 dispatch.py

Credentials come from .env:
    IMAP_EMAIL=thr.leelasithorn@gmail.com
    IMAP_PASSWORD=xxxx xxxx xxxx xxxx

This is identical to poller.py but runs once and exits (no loop).
"""

from __future__ import annotations

import csv
import imaplib
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import email as email_lib
from dotenv import load_dotenv

import parser as email_parser
import db as database

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

IMAP_SERVER   = "imap.gmail.com"
IMAP_PORT     = 993
IMAP_EMAIL    = os.getenv("IMAP_EMAIL", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")

DB_SRC   = Path(__file__).parent / "spending.db"
CSV_PATH = Path(__file__).parent / "transactions.csv"
IDS_PATH = Path(__file__).parent / "imported_ids.json"
TMP_DB   = Path("/tmp/bunshee_dispatch.db")

CSV_COLUMNS = [
    "id", "timestamp", "source", "merchant",
    "amount", "currency", "category", "clarification_needed", "notes",
]

WATCHED = [
    "onlineservice@ktc.co.th",
    "kplus@kasikornbank.com",
]

# ---------------------------------------------------------------------------
# ID tracking
# ---------------------------------------------------------------------------

def _load_ids() -> set[str]:
    try:
        with open(IDS_PATH) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_ids(ids: set[str]) -> None:
    with open(IDS_PATH, "w") as f:
        json.dump(sorted(ids), f, indent=2)


# ---------------------------------------------------------------------------
# DB helpers (FUSE-safe)
# ---------------------------------------------------------------------------

def _db_insert(tx: dict) -> int:
    try:
        conn = sqlite3.connect(str(DB_SRC))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("SELECT 1 FROM transactions LIMIT 1")
        used_tmp = False
    except Exception:
        shutil.copy2(str(DB_SRC), str(TMP_DB))
        conn = sqlite3.connect(str(TMP_DB))
        conn.execute("PRAGMA journal_mode=DELETE")
        used_tmp = True

    cur = conn.execute(
        """INSERT INTO transactions
           (timestamp, source, raw_text, merchant, amount, currency,
            category, confidence, clarification_needed, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            tx["timestamp"],
            tx["source"],
            tx.get("raw_text", ""),
            tx["merchant"],
            float(tx["amount"]),
            tx.get("currency", "THB"),
            tx.get("category", "Uncategorised"),
            0.0,
            int(tx.get("clarification_needed", False)),
            tx.get("notes", ""),
        ),
    )
    new_id = cur.lastrowid
    conn.commit()

    if used_tmp:
        conn.close()
        with open(TMP_DB, "rb") as f:
            data = f.read()
        with open(DB_SRC, "wb") as f:
            f.write(data)
    else:
        conn.close()

    return new_id


def _export_csv() -> int:
    try:
        conn = sqlite3.connect(str(DB_SRC))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY timestamp DESC"
        ).fetchall()
        conn.close()
    except Exception:
        shutil.copy2(str(DB_SRC), str(TMP_DB))
        conn = sqlite3.connect(str(TMP_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY timestamp DESC"
        ).fetchall()
        conn.close()

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    return len(rows)


# ---------------------------------------------------------------------------
# IMAP fetch
# ---------------------------------------------------------------------------

def _fetch_new(imap: imaplib.IMAP4_SSL, imported: set[str]) -> list[tuple[str, bytes]]:
    results = []
    for sender in WATCHED:
        typ, data = imap.search(None, f'FROM "{sender}"')
        if typ != "OK" or not data[0]:
            continue
        uids = data[0].split()
        for uid in uids[-50:]:       # only last 50 per sender
            uid_str = uid.decode()
            if uid_str in imported:
                continue
            try:
                typ2, msg_data = imap.fetch(uid, "(RFC822)")
                if typ2 == "OK" and msg_data and msg_data[0]:
                    results.append((uid_str, msg_data[0][1]))
            except Exception as exc:
                logger.warning("Fetch error uid=%s: %s", uid_str, exc)
    return results


def _email_timestamp(raw: bytes) -> str:
    try:
        msg = email_lib.message_from_bytes(raw)
        dt  = parsedate_to_datetime(msg.get("Date", ""))
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return datetime.now().isoformat()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    if not IMAP_EMAIL or not IMAP_PASSWORD:
        logger.error(
            "IMAP credentials missing.\n"
            "Set IMAP_EMAIL and IMAP_PASSWORD in bunshee-ai/.env"
        )
        return

    database.init_db()
    imported = _load_ids()

    logger.info("Connecting to Gmail IMAP…")
    imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    imap.login(IMAP_EMAIL, IMAP_PASSWORD)
    imap.select("INBOX")
    logger.info("Connected. Searching for new KTC / KBank emails…")

    new_emails = _fetch_new(imap, imported)
    try:
        imap.logout()
    except Exception:
        pass

    if not new_emails:
        logger.info("No new emails found — already up to date.")
        return

    logger.info("Found %d new email(s) to process.", len(new_emails))
    saved = 0

    for uid, raw in new_emails:
        email_type, parsed = email_parser.route(raw, {})

        if email_type is None or parsed is None:
            imported.add(uid)
            continue

        merchant    = parsed.get("merchant", "Unknown")
        amount      = float(parsed.get("amount") or 0)
        clarif_type = parsed.get("clarification_type")
        notes       = parsed.get("snippet", "")

        try:
            memory = database.get_merchant_memory(merchant)
        except Exception:
            memory = None

        needs_review = False
        category     = "Uncategorised"

        if clarif_type == "subscription_check":
            if memory is not None:
                category = memory.get("category") or "Subscription" if memory["is_subscription"] else "Uncategorised"
                notes   += f"\n[subscription_check: known={'yes' if memory['is_subscription'] else 'no'}, auto-applied]"
            else:
                needs_review = True
                notes += "\n[subscription_check: pending]"
        elif parsed.get("needs_clarification_hint"):
            needs_review = True

        tx_id = _db_insert({
            "source":               parsed["source"],
            "merchant":             merchant,
            "amount":               amount,
            "currency":             parsed.get("currency", "THB"),
            "timestamp":            _email_timestamp(raw),
            "raw_text":             parsed.get("raw_text", ""),
            "category":             category,
            "clarification_needed": needs_review,
            "notes":                notes,
        })

        imported.add(uid)
        saved += 1
        logger.info("✅  #%d  %s  ฿%.2f  [%s]%s",
                    tx_id, merchant, amount, email_type,
                    "  ⚠️  review needed" if needs_review else "")

    _save_ids(imported)

    if saved:
        total = _export_csv()
        logger.info("📄  CSV updated — %d total rows.", total)

    logger.info("Done — %d new transaction(s) saved.", saved)


if __name__ == "__main__":
    run()
