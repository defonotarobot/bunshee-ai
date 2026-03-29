"""
insert_transactions.py — Write parsed transactions into spending.db.

Works around the SQLite disk I/O error on FUSE-mounted filesystems (e.g. Cowork VM)
by operating on a /tmp copy of the DB and writing the bytes back via plain file I/O.

Usage (from Claude or a script):
    python3 insert_transactions.py transactions.json
    python3 insert_transactions.py --stdin   # read JSON from stdin

JSON format — list of transaction objects:
[
  {
    "source": "KBank",          # "KTC" or "KBank"
    "merchant": "7-ELEVEN",
    "amount": 95.0,
    "currency": "THB",          # optional, default THB
    "timestamp": "2026-03-21T20:59:43",  # optional, default now
    "raw_text": "...",          # optional
    "notes": "...",             # optional
    "clarification_needed": false,       # optional
    "gmail_id": "19d10b1e411aaabc"       # optional — stored to avoid re-import
  },
  ...
]

Outputs:
  - Inserts new transactions into spending.db (skips any already imported via gmail_id)
  - Regenerates transactions.csv
  - Prints summary to stdout
"""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_SRC   = Path(__file__).parent / "spending.db"
CSV_PATH = Path(__file__).parent / "transactions.csv"
IDS_PATH = Path(__file__).parent / "imported_ids.json"   # tracks Gmail IDs already imported
TMP_DB   = Path("/tmp/bunshee_insert.db")

CSV_COLUMNS = [
    "id", "timestamp", "source", "merchant",
    "amount", "currency", "category", "clarification_needed", "notes",
]

# ---------------------------------------------------------------------------

def _load_imported_ids() -> set[str]:
    try:
        with open(IDS_PATH) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_imported_ids(ids: set[str]) -> None:
    with open(IDS_PATH, "w") as f:
        json.dump(sorted(ids), f, indent=2)


def _get_db() -> tuple[sqlite3.Connection, bool]:
    """
    Open the DB.  On FUSE mounts, copy to /tmp first.
    Returns (conn, used_tmp_copy).
    """
    try:
        # Try direct open first (works natively on Mac)
        conn = sqlite3.connect(str(DB_SRC))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
        return conn, False
    except Exception:
        pass

    # FUSE fallback: copy to /tmp, work there
    shutil.copy2(str(DB_SRC), str(TMP_DB))
    conn = sqlite3.connect(str(TMP_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    return conn, True


def _writeback(conn: sqlite3.Connection, used_tmp: bool) -> None:
    conn.close()
    if used_tmp:
        with open(TMP_DB, "rb") as f:
            data = f.read()
        with open(DB_SRC, "wb") as f:
            f.write(data)


def _export_csv(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT * FROM transactions ORDER BY timestamp DESC"
    ).fetchall()
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    return len(rows)


# ---------------------------------------------------------------------------

def run(transactions: list[dict]) -> None:
    if not transactions:
        print("No transactions to insert.")
        return

    imported_ids = _load_imported_ids()
    conn, used_tmp = _get_db()

    inserted = 0
    skipped  = 0

    for tx in transactions:
        gmail_id = tx.get("gmail_id", "")

        if gmail_id and gmail_id in imported_ids:
            skipped += 1
            continue

        ts = tx.get("timestamp") or datetime.now().isoformat()

        conn.execute(
            """INSERT INTO transactions
               (timestamp, source, raw_text, merchant, amount, currency,
                category, confidence, clarification_needed, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                ts,
                tx.get("source", "KBank"),
                tx.get("raw_text", ""),
                tx.get("merchant", "Unknown"),
                float(tx.get("amount", 0)),
                tx.get("currency", "THB"),
                tx.get("category", "Uncategorised"),
                0.0,
                int(tx.get("clarification_needed", False)),
                tx.get("notes", ""),
            ),
        )

        if gmail_id:
            imported_ids.add(gmail_id)
        inserted += 1

    conn.commit()

    csv_rows = _export_csv(conn)
    _writeback(conn, used_tmp)
    _save_imported_ids(imported_ids)

    print(f"✅  Inserted {inserted} new transaction(s), skipped {skipped} duplicates.")
    print(f"📄  CSV updated — {csv_rows} total rows → {CSV_PATH.name}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stdin":
        data = json.load(sys.stdin)
    elif len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
    else:
        print("Usage: python3 insert_transactions.py <file.json>")
        print("       python3 insert_transactions.py --stdin")
        sys.exit(1)

    run(data)
