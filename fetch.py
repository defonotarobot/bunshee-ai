"""
fetch.py — Bunshee email fetcher.

Connects to Gmail IMAP, finds new KTC/KBank transaction emails, and saves
matching raw emails to pending/ for processing by process.py.

Dedup strategy:
  - Uses persistent IMAP UIDs (not sequence numbers — those shift on deletion).
  - UIDs already in pending/<*_uid{uid}.eml> or processed/<*_uid{uid}.eml>
    are skipped — the filesystem is the only state store.
  - On first run: migrates imported_ids.json → processed/ markers so old
    emails are not re-imported.

Credentials from bunshee-ai/.env:
    IMAP_EMAIL=thr.leelasithorn@gmail.com
    IMAP_PASSWORD=xxxx xxxx xxxx xxxx

Usage:
    python3 fetch.py
"""

from __future__ import annotations

import imaplib
import json
import logging
import os
import re
import email as email_lib
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path

from dotenv import load_dotenv

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

BASE_DIR      = Path(__file__).parent
FORMAT_DIR    = BASE_DIR / "email_format"
PENDING_DIR   = BASE_DIR / "pending"
PROCESSED_DIR = BASE_DIR / "processed"

LAST_FETCHED_FILE = BASE_DIR / "last_fetched.txt"
# Fallback lookback used only when last_fetched.txt doesn't exist.
LOOKBACK_DAYS_DEFAULT = 7

WATCHED = [
    "onlineservice@ktc.co.th",
    "kplus@kasikornbank.com",
]

# ---------------------------------------------------------------------------
# Format patterns — loaded from email_format/*.eml at startup
# ---------------------------------------------------------------------------

def _decode_subject(raw: str) -> str:
    parts = decode_header(raw or "")
    result = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            result.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(chunk)
    return "".join(result)


def _sender_email(from_header: str) -> str:
    m = re.search(r"[\w.+-]+@[\w.-]+", from_header)
    return m.group(0).lower() if m else from_header.lower().strip()


def load_format_patterns() -> dict[str, list[str]]:
    """
    Read every .eml in email_format/ and return:
        { sender_email_lower: [subject_keyword, ...] }
    """
    patterns: dict[str, list[str]] = {}
    if not FORMAT_DIR.exists():
        logger.warning("email_format/ directory not found — no format filtering applied.")
        return patterns
    for eml_path in sorted(FORMAT_DIR.glob("*.eml")):
        try:
            msg     = email_lib.message_from_bytes(eml_path.read_bytes())
            sender  = _sender_email(msg.get("From", ""))
            subject = _decode_subject(msg.get("Subject", ""))
            m = re.search(r"\([^)]+\)\s*$", subject)
            keyword = m.group(0).strip() if m else subject.strip()
            patterns.setdefault(sender, [])
            if keyword and keyword not in patterns[sender]:
                patterns[sender].append(keyword)
        except Exception as exc:
            logger.warning("Could not load format template %s: %s", eml_path.name, exc)
    logger.info("Format patterns: %s", patterns)
    return patterns


def _matches_format(raw_header: bytes, patterns: dict[str, list[str]]) -> bool:
    msg     = email_lib.message_from_bytes(raw_header)
    sender  = _sender_email(msg.get("From", ""))
    subject = _decode_subject(msg.get("Subject", ""))
    keywords = patterns.get(sender, [])
    if not keywords:
        return False
    subject_lower = subject.lower()
    return any(kw.lower() in subject_lower for kw in keywords)


# ---------------------------------------------------------------------------
# UID dedup — filesystem is the state store
# ---------------------------------------------------------------------------

def _uid_re() -> re.Pattern:
    return re.compile(r"_uid(\d+)\.eml$")


def _load_seen_uids() -> set[str]:
    """
    Build set of UIDs already fetched/processed from filenames in
    pending/ and processed/.  No extra state file needed.
    """
    uid_re = _uid_re()
    seen: set[str] = set()
    for directory in (PENDING_DIR, PROCESSED_DIR):
        if directory.exists():
            for f in directory.iterdir():
                m = uid_re.search(f.name)
                if m:
                    seen.add(m.group(1))
    return seen


def _migrate_legacy_ids() -> None:
    """
    One-time migration: if imported_ids.json exists, create empty marker
    files in processed/ for each UID so the new dedup logic skips them.
    Renames imported_ids.json to imported_ids.json.bak on completion.
    """
    legacy = BASE_DIR / "imported_ids.json"
    if not legacy.exists():
        return
    try:
        with open(legacy) as f:
            old_ids: list[str] = json.load(f)
    except Exception as exc:
        logger.warning("Could not read imported_ids.json: %s", exc)
        return

    PROCESSED_DIR.mkdir(exist_ok=True)
    count = 0
    for uid in old_ids:
        marker = PROCESSED_DIR / f"migrated_uid{uid}.eml"
        if not marker.exists():
            marker.write_bytes(b"")
            count += 1

    legacy.rename(BASE_DIR / "imported_ids.json.bak")
    logger.info("Migrated %d legacy UIDs to processed/ — imported_ids.json backed up.", count)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> int:
    """
    Fetch new matching emails to pending/.
    Returns the number of .eml files saved.
    """
    if not IMAP_EMAIL or not IMAP_PASSWORD:
        logger.error(
            "IMAP credentials missing.\n"
            "Set IMAP_EMAIL and IMAP_PASSWORD in bunshee-ai/.env"
        )
        return 0

    patterns = load_format_patterns()
    if not patterns:
        logger.error("No format patterns loaded — aborting to avoid importing junk.")
        return 0

    # One-time migration from imported_ids.json
    _migrate_legacy_ids()

    seen_uids = _load_seen_uids()
    PENDING_DIR.mkdir(exist_ok=True)

    # SINCE window: use last_fetched.txt if it exists, else default lookback
    try:
        since_date = datetime.fromisoformat(LAST_FETCHED_FILE.read_text().strip())
        # Go back 1 extra day so IMAP SINCE (day-level) doesn't miss edge cases;
        # UID dedup prevents actual re-imports.
        since_str = (since_date - timedelta(days=1)).strftime("%d-%b-%Y")
    except Exception:
        since_str = (datetime.now() - timedelta(days=LOOKBACK_DAYS_DEFAULT)).strftime("%d-%b-%Y")
    logger.info("Connecting to Gmail IMAP (SINCE %s)…", since_str)

    imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    imap.login(IMAP_EMAIL, IMAP_PASSWORD)
    imap.select("INBOX")

    fetched = 0

    for sender in WATCHED:
        # Use UID-based search so IDs are persistent even if emails are deleted
        typ, data = imap.uid("search", None, f'FROM "{sender}" SINCE "{since_str}"')
        if typ != "OK" or not data[0]:
            continue

        uids = data[0].split()
        logger.info("%d candidate UID(s) from %s", len(uids), sender)

        for uid_bytes in uids:
            uid_str = uid_bytes.decode()

            if uid_str in seen_uids:
                logger.debug("UID %s already seen — skipping", uid_str)
                continue

            try:
                # Fetch headers only first — check format before downloading body
                t_hdr, hdr_data = imap.uid("fetch", uid_bytes, "(RFC822.HEADER)")
                if t_hdr != "OK" or not hdr_data or not hdr_data[0]:
                    continue

                raw_header = hdr_data[0][1]

                if not _matches_format(raw_header, patterns):
                    logger.debug("UID %s skipped — subject does not match any format template", uid_str)
                    seen_uids.add(uid_str)  # remember to avoid re-checking headers
                    continue

                # Format matched — fetch full body
                t_body, body_data = imap.uid("fetch", uid_bytes, "(RFC822)")
                if t_body != "OK" or not body_data or not body_data[0]:
                    continue

                # Save to pending/ with UID embedded in filename for dedup
                ts       = datetime.now().strftime("%Y%m%dT%H%M%S%f")
                filename = f"{ts}_uid{uid_str}.eml"
                (PENDING_DIR / filename).write_bytes(body_data[0][1])
                seen_uids.add(uid_str)
                fetched += 1
                logger.info("✉️  Saved UID %s → pending/%s", uid_str, filename)

            except Exception as exc:
                logger.warning("Error processing UID %s: %s", uid_str, exc)

    try:
        imap.logout()
    except Exception:
        pass

    # Update last_fetched so the next run's SINCE window starts from now
    LAST_FETCHED_FILE.write_text(datetime.now().isoformat())

    logger.info("Done — %d new email(s) saved to pending/.", fetched)
    return fetched


if __name__ == "__main__":
    run()
