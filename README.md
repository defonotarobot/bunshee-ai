# bunshee-ai — Personal Spending Tracker

Monitors KTC credit card and KBank QR payment emails, parses transactions automatically,
and lets **Claude (Cowork)** act as the brain for categorisation, Q&A, and analysis.

---

## Architecture

```
Gmail inbox
    │
    ▼  (IMAP IDLE — push, no polling)
watcher.py ──────────────────────────────► pending/*.eml
    │                                           │
    │                               ┌───────────┘
    │                               ▼  (Cowork scheduled task, every 5 min)
    │                       process_pending.py
    │                               │
    │                               ▼
    │                         spending.db  (SQLite)
    │                               │
    ▼                               ▼
agent.py                    Claude (Cowork)  ◄── you ask questions here
(runs watcher + FastAPI)            │
    │                               │  classifies, answers, queries DB directly
    ▼                               ▼
localhost:3000              macOS notifications
(React dashboard)           (on new transactions)
```

### What each file does

| File | Role |
|---|---|
| `watcher.py` | IMAP IDLE loop — saves matching emails to `pending/` |
| `process_pending.py` | Processes `pending/` → saves to DB → macOS notification |
| `agent.py` | Starts watcher + FastAPI dashboard |
| `db.py` | SQLite helpers (transactions, subscriptions, classification rules) |
| `parser.py` | KTC + KBank + subscription regex extraction |
| `server.py` | FastAPI REST API + WebSocket for dashboard |
| `dashboard/` | React app (5 tabs: Dashboard, Transactions, Subscriptions, Budgets, Settings) |

### What Claude (Cowork) does

Claude is the brain. You talk to it directly in the Cowork app. It can:
- **Categorise transactions** — reads `Uncategorised` records from the DB and updates them
- **Answer questions** — "what did I spend this week?", "how much on coffee this month?"
- **Budget status** — "am I over budget on food?"
- **Subscription review** — "which subscriptions are renewing soon?"
- **Run process_pending.py** on demand when you ask it to sync
- **Query the DB directly** using Python when you ask spending questions

---

## Setup

### 1. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Configure credentials

Edit `.env` in this folder:

```env
IMAP_SERVER=imap.gmail.com
IMAP_EMAIL=thr.leelasithorn@gmail.com
IMAP_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password
```

**Gmail App Password:** Google Account → Security → 2-Step Verification → App Passwords → create one called "Spending Tracker".

### 3. Build the dashboard (one-time)

```bash
cd dashboard && npm install && npm run build && cd ..
```

### 4. Start the agent

```bash
python3 agent.py
```

This starts the IMAP watcher and the dashboard server. Keep this running.

### 5. Auto-start on login (optional)

To start automatically when your Mac boots, create a launchd plist:

```bash
# Edit the path below to match your actual repo location
cat > ~/Library/LaunchAgents/com.bunshee.agent.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bunshee.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/YOUR/PATH/TO/bunshee-ai/agent.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/YOUR/PATH/TO/bunshee-ai</string>
    <key>StandardOutPath</key>
    <string>/tmp/bunshee-agent.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/bunshee-agent-error.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.bunshee.agent.plist
```

---

## Talking to Claude (Cowork)

All updates are **on-demand** — open Cowork and ask naturally.
Claude runs `process_pending.py` and queries `spending.db` directly to answer.

| You say | What Claude does |
|---|---|
| "Any new transactions?" | Runs process_pending.py, shows what was saved |
| "What did I spend today?" | Queries DB for today's transactions |
| "Categorise my recent transactions" | Reads Uncategorised rows, assigns categories, updates DB |
| "How much on food this month?" | Queries DB filtered by category + month |
| "Am I over budget?" | Compares spending to config.json budget limits |
| "Any subscriptions renewing soon?" | Queries subscriptions table |
| "Give me a full monthly summary" | Full breakdown by category + budget status |

### Daily report

A Cowork scheduled task ("bunshee-daily-report") runs automatically at **21:00 every day**.
It processes any pending emails and shows a spending summary.
Manage it in the Cowork sidebar → Scheduled.

---

## Dashboard

Visit **http://localhost:3000** in any browser (or via Tailscale from iPhone).

Tabs: Dashboard · Transactions · Subscriptions · Budgets · Settings

---

## Email filters

Tracked senders (configured in `config.json`):
- **KTC:** `onlineservice@ktc.co.th`
- **KBank:** `kplus@kasikornbank.com`
- **Subscriptions:** Netflix, Spotify, Apple, Google, Microsoft, etc.

To add a new sender, add it to `config.json → filters → subscriptions`.

---

## Data

All data lives in `spending.db` (SQLite) in this folder. Three tables:

- `transactions` — every parsed payment
- `subscriptions` — auto-detected recurring charges
- `classification_rules` — patterns Claude saves for future auto-categorisation

---

## File structure

```
bunshee-ai/
  agent.py              ← start here: runs watcher + dashboard
  watcher.py            ← IMAP IDLE, saves to pending/
  process_pending.py    ← processes pending/ → DB + notification
  db.py                 ← SQLite helpers
  parser.py             ← KTC + KBank email regex
  server.py             ← FastAPI (dashboard API + WebSocket)
  config.json           ← settings (budgets, filters, etc.)
  .env                  ← secrets (IMAP password) — never commit
  pending/              ← raw .eml files waiting to be processed
  processed/            ← processed .eml archive
  email_format/         ← sample .eml files used to build regex
  dashboard/            ← React frontend
    src/
      App.jsx
      components/
        Dashboard.jsx
        Transactions.jsx
        Subscriptions.jsx
        Budgets.jsx
        Settings.jsx
```
