"""
run_dashboard.py — Start the Bunshee dashboard + auto-sync.

Launches:
  1. FastAPI server on port 3000 (dashboard + REST API)
  2. Background poller that runs fetch.py → process.py every 60 seconds

Usage:
    python3 run_dashboard.py

Then open: http://localhost:3000
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.json"
PROJECT_DIR = Path(__file__).parent
POLL_INTERVAL = 60  # seconds


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        cfg.setdefault("imap", {})
        cfg["imap"]["email"]    = os.getenv("IMAP_EMAIL",    cfg["imap"].get("email",    ""))
        cfg["imap"]["password"] = os.getenv("IMAP_PASSWORD", cfg["imap"].get("password", ""))
        return cfg
    except Exception as e:
        logging.warning("Could not load config.json: %s — using defaults", e)
        return {}


def _poll_loop():
    """Background thread: fetch new emails then process them, every 60s."""
    logger.info("🔄  Auto-sync started — polling every %ds", POLL_INTERVAL)
    while True:
        try:
            for script in ["fetch.py", "process.py"]:
                result = subprocess.run(
                    [sys.executable, str(PROJECT_DIR / script)],
                    capture_output=True, text=True, cwd=str(PROJECT_DIR),
                    timeout=120,
                )
                if result.returncode != 0 and result.stderr:
                    logger.warning("%s error: %s", script, result.stderr.strip()[-200:])
        except Exception as exc:
            logger.error("Poll cycle error: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    import db as database
    from server import create_app

    config = _load_config()
    database.init_db()

    app = create_app(config, database)

    # Start background auto-sync thread
    poll_thread = threading.Thread(target=_poll_loop, daemon=True)
    poll_thread.start()

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("  Bunshee dashboard → http://localhost:3000")
    logger.info("  Auto-sync: every %ds", POLL_INTERVAL)
    logger.info("  Ctrl+C to stop")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="warning")
