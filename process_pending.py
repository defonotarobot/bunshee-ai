"""
process_pending.py — Email processor, run on a schedule via Cowork.

Reads .eml files from ./pending/, parses them with parser.py,
saves structured records to spending.db, fires a macOS notification,
then moves the file to ./processed/.

Transactions are saved with category="Uncategorised" and confidence=0.
Claude (Cowork) classifies them when you ask: "categorise my recent transactions."

Usage:
    python3 process_pending.py          # process whatever is in pending/
"""

import csv
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import db as database
import parser as email_parser

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

PENDING_DIR   = Path(__file__).parent / "pending"
PROCESSED_DIR = Path(__file__).parent / "processed"
CSV_PATH      = Path(__file__).parent / "transactions.csv"

PENDING_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

CONFIG_PATH = Path(__file__).parent / "config.json"

CSV_COLUMNS = [
    "id", "timestamp", "source", "merchant",
    "amount", "currency", "category", "clarification_needed", "notes",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _export_csv() -> None:
    """Regenerate transactions.csv from the full DB — always a complete, up-to-date export."""
    rows = database.get_transactions(limit=100_000)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    logger.info("📄  CSV updated → %s  (%d rows)", CSV_PATH.name, len(rows))


def _notify(title: str, body: str) -> None:
    """Fire a native macOS notification."""
    script = f'display notification "{body}" with title "{title}" sound name "default"'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception as exc:
        logger.debug("Notification failed: %s", exc)


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def process_file(path: Path, config: dict) -> bool:
    """
    Parse one .eml → save to DB → notify.
    Returns True if a transaction was saved.
    """
    try:
        raw = path.read_bytes()
        email_type, parsed = email_parser.route(raw, config)

        if email_type is None or parsed is None:
            logger.info("Non-tracked email skipped: %s", path.name)
            return False

        merchant   = parsed.get("merchant", "Unknown")
        amount     = parsed.get("amount") or 0.0
        clarif_type = parsed.get("clarification_type")

        # Check merchant memory first — never ask the same merchant twice
        memory = database.get_merchant_memory(merchant)
        category     = "Uncategorised"
        needs_review = False
        notes        = parsed.get("snippet", "")

        if clarif_type == "subscription_check":
            if memory is not None:
                # Already know the answer — apply silently
                if memory["is_subscription"]:
                    category = memory.get("category") or "Subscription"
                    notes += "\n[subscription_check: known=yes, auto-applied]"
                else:
                    notes += "\n[subscription_check: known=no]"
            else:
                # Unknown merchant — flag for review
                needs_review = True
                notes += "\n[subscription_check: pending]"
        elif parsed.get("needs_clarification_hint"):
            needs_review = True

        tx_id = database.insert_transaction(
            source               = parsed["source"],
            raw_text             = parsed.get("raw_text", ""),
            merchant             = merchant,
            amount               = amount,
            currency             = parsed.get("currency", "THB"),
            category             = category,
            confidence           = 0.0,
            clarification_needed = needs_review,
            notes                = notes,
        )

        logger.info("✅  Saved tx #%d — %s  ฿%.2f  [%s]", tx_id, merchant, amount, email_type)

        if needs_review:
            _notify(
                "💸 New Transaction — Needs Review",
                f"{merchant}  ฿{amount:,.0f}  · Open Cowork to categorise",
            )
        else:
            _notify(
                f"💸 {email_type} Transaction",
                f"{merchant}  ฿{amount:,.0f}",
            )

        return True

    except Exception as exc:
        logger.error("Error processing %s: %s", path.name, exc)
        return False


def run() -> None:
    database.init_db()
    config = _load_config()

    files = sorted(PENDING_DIR.glob("*.eml"))
    if not files:
        logger.info("Nothing in pending/ — all clear.")
        return

    logger.info("Processing %d pending file(s)…", len(files))
    saved = 0

    for path in files:
        ok   = process_file(path, config)
        dest = PROCESSED_DIR / path.name
        path.rename(dest)
        if ok:
            saved += 1

    logger.info("Done — %d transaction(s) saved to DB.", saved)

    # Always regenerate the CSV so it reflects the full current state
    _export_csv()

    if saved:
        _notify(
            "💸 Spending Tracker",
            f"{saved} new transaction(s) saved. Ask Claude for a summary.",
        )


if __name__ == "__main__":
    run()
