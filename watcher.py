"""
watcher.py — Lightweight IMAP IDLE email watcher.

Monitors Gmail inbox for KTC and KBank emails only.
When a matching email arrives, saves the raw .eml to ./pending/.
That's it. No Claude API calls, no classification, no Telegram.

Watched senders:
    KTC:   Onlineservice@ktc.co.th
    KBank: KPLUS@kasikornbank.com

Claude (Cowork) + process_pending.py handle everything else.

Run once at login:
    python3 watcher.py

Or set up via launchd so it starts automatically on boot.
"""

import email
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

import imaplib2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

PENDING_DIR = Path(__file__).parent / "pending"
PENDING_DIR.mkdir(exist_ok=True)

CONFIG_PATH = Path(__file__).parent / "config.json"

# KTC + KBank senders — the only emails we care about
WATCHED_SENDERS = {
    "onlineservice@ktc.co.th",
    "kplus@kasikornbank.com",
}


# ---------------------------------------------------------------------------
# Config (IMAP credentials only)
# ---------------------------------------------------------------------------

def _imap_creds() -> tuple[str, str, str]:
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    server   = os.getenv("IMAP_SERVER",   cfg.get("imap", {}).get("server",   "imap.gmail.com"))
    user     = os.getenv("IMAP_EMAIL",    cfg.get("imap", {}).get("email",    ""))
    password = os.getenv("IMAP_PASSWORD", cfg.get("imap", {}).get("password", ""))
    return server, user, password


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_watched(raw: bytes, watched: set[str]) -> bool:
    """Fast sender check — no full parse needed."""
    try:
        msg    = email.message_from_bytes(raw)
        sender = msg.get("From", "").lower()
        return any(s in sender for s in watched)
    except Exception:
        return False


def _save(raw: bytes) -> None:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = PENDING_DIR / f"{ts}.eml"
    path.write_bytes(raw)
    logger.info("📥  Saved → pending/%s", path.name)


def _fetch_unseen(imap, watched: set[str]) -> int:
    typ, data = imap.search(None, "UNSEEN")
    if typ != "OK" or not data[0]:
        return 0
    count = 0
    for uid in data[0].split():
        try:
            t2, msg_data = imap.fetch(uid, "(RFC822)")
            if t2 == "OK" and msg_data and msg_data[0]:
                raw = msg_data[0][1]
                if _is_watched(raw, watched):
                    _save(raw)
                    count += 1
        except Exception as exc:
            logger.error("Fetch error uid=%s: %s", uid, exc)
    return count


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run() -> None:
    server, user, password = _imap_creds()
    if not password:
        logger.error("IMAP_PASSWORD not set. Add it to .env and restart.")
        return

    logger.info("Watching senders: %s", WATCHED_SENDERS)

    while True:
        try:
            logger.info("Connecting to %s as %s …", server, user)
            imap = imaplib2.IMAP4_SSL(server)
            imap.login(user, password)
            imap.select("INBOX")
            logger.info("✅  Connected. IMAP IDLE active.")

            # Drain any backlog that arrived while we were offline
            n = _fetch_unseen(imap, WATCHED_SENDERS)
            if n:
                logger.info("Saved %d backlog email(s) to pending/", n)

            # IDLE loop
            while True:
                done = threading.Event()
                imap.idle(callback=lambda _: done.set(), timeout=28 * 60)
                done.wait(timeout=29 * 60)
                _fetch_unseen(imap, WATCHED_SENDERS)

        except Exception as exc:
            logger.error("IMAP error: %s — reconnecting in 30 s", exc)
            threading.Event().wait(30)


if __name__ == "__main__":
    run()
