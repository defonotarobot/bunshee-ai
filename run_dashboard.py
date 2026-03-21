"""
run_dashboard.py — Start just the dashboard server on port 3000.
No IMAP watcher, no scheduler. Good for viewing data and the UI.

Usage:
    python3 run_dashboard.py

Then open: http://localhost:3000
"""

import json
import logging
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)

CONFIG_PATH = Path(__file__).parent / "config.json"


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


if __name__ == "__main__":
    import db as database
    from server import create_app

    config = _load_config()
    database.init_db()

    app = create_app(config, database)

    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logging.info("  Bunshee dashboard → http://localhost:3000")
    logging.info("  Ctrl+C to stop")
    logging.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="warning")
