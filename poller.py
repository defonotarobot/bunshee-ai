"""
poller.py — Runs fetch → process every 60 seconds.

Usage (run once in a terminal, leave it running):
    cd bunshee-ai
    python3 poller.py
"""

import logging
import time

import fetch
import process

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 60  # seconds


def run() -> None:
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("  Bunshee poller — polling every %ds", POLL_INTERVAL)
    logger.info("  Ctrl+C to stop")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    while True:
        try:
            fetched = fetch.run()
            if fetched:
                process.run()
        except Exception as exc:
            logger.error("Poll cycle error: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
