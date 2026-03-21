"""
agent.py — Starts the two persistent services:

  1. watcher.py  — IMAP IDLE loop, saves matching emails to pending/
  2. server.py   — FastAPI dashboard on localhost:3000

Classification and Q&A is handled by Claude (Cowork), not this process.
process_pending.py runs on a schedule (via Cowork) to drain the pending/ folder.

Usage:
    python3 agent.py
"""

import asyncio
import json
import logging
import os
import threading
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

import db as database
from server import create_app

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.json"


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    cfg.setdefault("imap", {})
    cfg["imap"]["server"]   = os.getenv("IMAP_SERVER",   cfg["imap"].get("server",   "imap.gmail.com"))
    cfg["imap"]["email"]    = os.getenv("IMAP_EMAIL",    cfg["imap"].get("email",    ""))
    cfg["imap"]["password"] = os.getenv("IMAP_PASSWORD", cfg["imap"].get("password", ""))
    return cfg


async def main() -> None:
    config = _load_config()
    database.init_db()
    logger.info("Database ready at %s", database.DB_PATH)

    # Start IMAP watcher in a background daemon thread
    from watcher import run as watcher_run
    t = threading.Thread(target=watcher_run, daemon=True, name="imap-watcher")
    t.start()
    logger.info("IMAP watcher started")

    # Start FastAPI dashboard
    fastapi_app = create_app(config, database)
    uvi_cfg     = uvicorn.Config(fastapi_app, host="0.0.0.0", port=3000, log_level="warning")
    uvi_server  = uvicorn.Server(uvi_cfg)

    logger.info("Dashboard → http://localhost:3000")
    logger.info("Ask Claude (Cowork) to categorise transactions or answer spending questions.")

    await uvi_server.serve()


if __name__ == "__main__":
    asyncio.run(main())
