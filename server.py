"""
FastAPI server — REST API for the dashboard + WebSocket for live updates.
Serves the built React app from dashboard/dist/ at the root path.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

_ws_clients: list[WebSocket] = []


# ---------------------------------------------------------------------------
# WebSocket broadcast helper (called from agent.py after new transactions)
# ---------------------------------------------------------------------------

async def broadcast(event: str, data: dict) -> None:
    if not _ws_clients:
        return
    payload = json.dumps({"event": event, "data": data})
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            _ws_clients.discard(ws) if hasattr(_ws_clients, "discard") else None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config: dict, db) -> FastAPI:
    app = FastAPI(title="Spending Tracker", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Transactions -------------------------------------------------------

    @app.get("/api/transactions")
    async def get_transactions(
        limit:    int = Query(100, ge=1, le=1000),
        source:   str = Query(None),
        category: str = Query(None),
        month:    str = Query(None),
    ):
        return db.get_transactions(limit=limit, source=source,
                                   category=category, month=month)

    # ---- Subscriptions ------------------------------------------------------

    @app.get("/api/subscriptions")
    async def get_subscriptions():
        return db.get_subscriptions()

    # ---- Summary / charts ---------------------------------------------------

    @app.get("/api/summary")
    async def get_summary(month: str = Query(None)):
        if not month:
            month = datetime.now().strftime("%Y-%m")
        summary = db.get_monthly_summary(month)
        daily   = db.get_daily_spending(month)
        budget  = config.get("budgets", {})
        return {
            **summary,
            "daily":              daily,
            "budget_total":       budget.get("total", 0),
            "budget_per_category": budget.get("per_category", {}),
        }

    # ---- Budgets ------------------------------------------------------------

    @app.get("/api/budgets")
    async def get_budgets():
        month   = datetime.now().strftime("%Y-%m")
        summary = db.get_monthly_summary(month)
        budget  = config.get("budgets", {})
        return {
            "month":        month,
            "total_spent":  summary["total"],
            "total_budget": budget.get("total", 0),
            "per_category": {
                cat: {
                    "spent": summary["categories"].get(cat, 0),
                    "limit": lim,
                }
                for cat, lim in budget.get("per_category", {}).items()
            },
        }

    @app.put("/api/budgets")
    async def update_budgets(payload: dict):
        """Persist budget changes to config.json."""
        cfg_path = Path(__file__).parent / "config.json"
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = json.load(f)
            cfg["budgets"] = payload
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)
        config["budgets"] = payload
        return {"status": "ok"}

    # ---- Config (non-sensitive) ---------------------------------------------

    @app.get("/api/config")
    async def get_config():
        safe_keys = {"budgets", "alert_threshold", "report_time", "currency", "language"}
        return {k: v for k, v in config.items() if k in safe_keys}

    @app.put("/api/config")
    async def update_config(payload: dict):
        safe_keys = {"budgets", "alert_threshold", "report_time", "currency", "language"}
        cfg_path = Path(__file__).parent / "config.json"
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = json.load(f)
            for k, v in payload.items():
                if k in safe_keys:
                    cfg[k] = v
                    config[k] = v
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)
        return {"status": "ok"}

    # ---- Reviews (transactions needing clarification) -----------------------

    @app.get("/api/reviews")
    async def get_reviews():
        return db.get_pending_reviews()

    @app.post("/api/reviews/{tx_id}/resolve")
    async def resolve_review(tx_id: int, payload: dict):
        """
        Resolve a pending review.
        Body: { merchant, category, is_subscription (bool|null), answer (str) }
        """
        tx = db.get_transaction_by_id(tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")

        category       = payload.get("category", "Uncategorised")
        is_subscription = payload.get("is_subscription")  # bool or None
        answer         = payload.get("answer", "").strip()
        merchant       = payload.get("merchant") or tx.get("merchant", "")

        # Append answer to existing notes
        original_notes = tx.get("notes") or ""
        new_notes = original_notes.replace("[subscription_check: pending]", "").strip()
        if answer:
            new_notes += f"\n[Resolved: {answer}]"

        db.update_transaction(
            tx_id,
            category=category,
            notes=new_notes.strip(),
            clarification_needed=False,
        )

        # Persist merchant knowledge so we never ask again
        if is_subscription is not None and merchant:
            db.set_merchant_memory(
                merchant,
                is_subscription=is_subscription,
                category=category if is_subscription else None,
            )

        return {"status": "ok", "tx_id": tx_id}

    # ---- Manual sync --------------------------------------------------------

    @app.post("/api/sync")
    async def trigger_sync():
        """Run fetch.py then process.py — fetch new emails, then parse and insert."""
        import asyncio, sys
        project_dir = str(Path(__file__).parent)
        results = {}
        for script in ["fetch.py", "process.py"]:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(Path(__file__).parent / script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            stdout, stderr = await proc.communicate()
            out = stdout.decode()
            err = stderr.decode()
            results[script] = {"output": out, "error": err if err else None}
        return {"status": "sync_triggered", **results}

    # ---- WebSocket ----------------------------------------------------------

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        _ws_clients.append(ws)
        try:
            while True:
                await ws.receive_text()   # keep-alive; client can ping
        except WebSocketDisconnect:
            if ws in _ws_clients:
                _ws_clients.remove(ws)

    # ---- Static files (React build or plain HTML fallback) ------------------

    dist      = Path(__file__).parent / "dashboard" / "dist"
    dashboard = Path(__file__).parent / "dashboard"

    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")
    elif dashboard.exists():
        # Serve dashboard/index.html + manifest.json + icon.svg directly
        app.mount("/", StaticFiles(directory=str(dashboard), html=True), name="static")
    else:
        @app.get("/")
        async def root():
            return {"message": "Place dashboard/index.html to serve the UI."}

    return app
