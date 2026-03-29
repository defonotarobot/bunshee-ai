"""
process.py — Bunshee email processor.

Reads raw .eml files from pending/, parses them with parser.py, inserts
transactions into spending.db, regenerates transactions.csv, then moves
each file to processed/.

FUSE note: SQLite WAL mode fails on the VM's FUSE-mounted Mac filesystem.
Workaround: copy DB to /tmp, operate there, write raw bytes back at the end.

Called by:
  - poller.py      (after fetch.run() finds new emails)
  - server.py      (/api/sync — after fetch.py subprocess completes)
  - Cowork session (on-demand: python3 process.py)

Usage:
    python3 process.py
"""

from __future__ import annotations

import csv
import logging
import shutil
import sqlite3
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import email as email_lib

import parser as email_parser
import db as database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR      = Path(__file__).parent
PENDING_DIR   = BASE_DIR / "pending"
PROCESSED_DIR = BASE_DIR / "processed"
DB_SRC        = BASE_DIR / "spending.db"
CSV_PATH      = BASE_DIR / "transactions.csv"
TMP_DB        = Path("/tmp/bunshee_process.db")

CSV_COLUMNS = [
    "id", "timestamp", "source", "merchant",
    "amount", "currency", "category", "clarification_needed", "notes",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _email_timestamp(raw: bytes) -> str:
    try:
        msg = email_lib.message_from_bytes(raw)
        dt  = parsedate_to_datetime(msg.get("Date", ""))
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return datetime.now().isoformat()


def _export_csv() -> int:
    """Read from TMP_DB and write CSV. Returns row count."""
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


def _writeback_db() -> None:
    """Copy /tmp DB back to the Mac filesystem (raw bytes — avoids FUSE WAL)."""
    import sqlite3 as _sql
    # Force WAL checkpoint so ALL data is in the main DB file before we read bytes.
    # Without this, recent writes may still be in the -wal file and get lost.
    conn = _sql.connect(str(TMP_DB))
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    with open(TMP_DB, "rb") as f:
        data = f.read()
    with open(DB_SRC, "wb") as f:
        f.write(data)

    # Clear any stale WAL/SHM files for the target so the server doesn't
    # replay old journal entries on top of the freshly-written DB.
    for suffix in ("-wal", "-shm"):
        p = Path(str(DB_SRC) + suffix)
        if p.exists():
            try:
                p.write_bytes(b"")
            except Exception:
                pass  # best-effort on FUSE


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> int:
    """
    Process all pending .eml files.
    Returns the number of transactions successfully inserted.
    """
    if not PENDING_DIR.exists():
        logger.info("No pending/ directory — nothing to process.")
        return 0

    pending = sorted(PENDING_DIR.glob("*.eml"))
    if not pending:
        logger.info("No pending emails to process.")
        return 0

    PROCESSED_DIR.mkdir(exist_ok=True)

    # FUSE-safe: copy DB to /tmp so WAL mode works
    if DB_SRC.exists():
        shutil.copy2(str(DB_SRC), str(TMP_DB))
    database.DB_PATH = TMP_DB
    database.init_db()

    saved = 0

    for eml_path in pending:
        raw = eml_path.read_bytes()
        if not raw:
            # Empty marker file (e.g. from migration) — move to processed and skip
            eml_path.rename(PROCESSED_DIR / eml_path.name)
            continue

        email_type, parsed = email_parser.route(raw, {})

        if email_type is None or parsed is None:
            logger.info("⏭️  %s — not a recognised transaction, skipping", eml_path.name)
            eml_path.rename(PROCESSED_DIR / eml_path.name)
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
                category = (memory.get("category") or "Subscription") if memory["is_subscription"] else "Uncategorised"
                notes   += f"\n[subscription_check: known={'yes' if memory['is_subscription'] else 'no'}, auto-applied]"
            else:
                needs_review = True
                notes += "\n[subscription_check: pending]"
        elif parsed.get("needs_clarification_hint"):
            needs_review = True

        # Insert directly via sqlite3 (database.DB_PATH already points to TMP_DB)
        conn = sqlite3.connect(str(TMP_DB))
        cur = conn.execute(
            """INSERT INTO transactions
               (timestamp, source, raw_text, merchant, amount, currency,
                category, confidence, clarification_needed, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                _email_timestamp(raw),
                parsed["source"],
                parsed.get("raw_text", ""),
                merchant,
                amount,
                parsed.get("currency", "THB"),
                category,
                0.0,
                int(needs_review),
                notes,
            ),
        )
        tx_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Move to processed/ only after successful DB insert
        eml_path.rename(PROCESSED_DIR / eml_path.name)
        saved += 1
        logger.info(
            "✅  #%d  %s  ฿%.2f  [%s]%s",
            tx_id, merchant, amount, email_type,
            "  ⚠️  review needed" if needs_review else "",
        )

    if saved:
        total = _export_csv()
        _writeback_db()
        logger.info("📄  CSV updated — %d total rows.", total)

    logger.info("Done — %d new transaction(s) saved.", saved)
    return saved


if __name__ == "__main__":
    run()
