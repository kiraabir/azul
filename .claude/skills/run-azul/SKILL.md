---
name: run-azul
description: Build, run, and drive AZUL - the wallet-based loyalty card platform. Use when asked to start AZUL, test customer flows, generate wallet passes, or interact with the running app.
---

# AZUL - Wallet-Based Loyalty Card Platform

AZUL is a digital loyalty card platform for local businesses in Morocco. It supports Apple Wallet, Google Wallet, SMS engagement, and feedback loops.

**Drive via:** `python app.py` starts the Flask dev server, then use `npx playwright cli` or `node .claude/skills/run-azul/driver.mjs` to interact.

## Prerequisites

All prerequisites are installed in the project's venv and node_modules. No apt-get install needed on Windows.

```powershell
# Python venv already created, node_modules already installed
# Just activate/create them if needed:
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
npm install
```

## Setup

One-time setup after clone:

```powershell
# Install browser for Playwright
npx playwright install chromium

# Set secret key (required for production, optional for dev)
$env:SECRET_KEY = 'dev-secret-key-change-in-production'
```

## Build

No separate build step - it's a Flask app.

```powershell
# Database is auto-initialized on first run
python -m client.app  # or python app.py
```

## Run (agent path)

**Start the server in background:**

```powershell
# From project root
$env:SECRET_KEY = 'dev-secret-key-change-in-production'
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "app.py" -NoNewWindow
```

Wait for server: `timeout 30 bash -c 'until curl -sf http://localhost:5000/ >/dev/null; do sleep 1; done'`

**Drive the app with playwright-cli:**

```powershell
# Open dashboard
npx playwright-cli open http://localhost:5000/

# Interactive commands (in browser session):
npx playwright-cli cli snapshot      # Get element refs
npx playwright-cli cli fill "input[placeholder='e.g. Ahmed Benali']" "Ahmed Benali"
npx playwright-cli cli click "button:has-text('Continue to Wallet')"
npx playwright-cli cli screenshot      # Capture full page
npx playwright-cli cli close           # Close browser
```

**Or use the driver script:**

```powershell
node .claude\skills\run-azul\driver.mjs
```

**Screenshots:** `screenshots/` directory

**Server logs:** `server.log` and `server.err`

| command | what it does |
|---|---|
| `Start server` | Launches Flask dev server on http://localhost:5000 |
| `npx playwright-cli open <url>` | Open page in browser |
| `npx playwright-cli cli` | Interactive browser REPL |
| `npx playwright-cli screenshot <url> <path>` | Take screenshot and save |
| `node driver.mjs` | Run complete customer flow demo |

## Run (human path)

```powershell
.\run.ps1   # Starts server: python -m client.app
```

Ctrl-C to stop. Opens http://localhost:5000/ in browser.

## Test

```powershell
# Unit tests
.\venv\Scripts\pytest.exe tests/ -v

# Smoke test (customer -> card -> earn flow)
.\venv\Scripts\python.exe tests/smoke.py
```

## Gotchas

- **SECRET_KEY required:** Set it or use `dev-secret-key-change-in-production` for local dev
- **Port conflict:** If port 5000 is busy, find and kill the process: `netstat -ano | findstr :5000` then `taskkill /PID <pid> /F`
- **Playwright browser:** Must run `npx playwright install chromium` on a fresh machine
- **Debug mode:** Server runs in debug mode with reloader (two python processes); use single process for cleaner shutdown
- **Database:** SQLite file `azul.db` is created on first run

## Troubleshooting

- **Connection refused:** Server not running -> start it with `SECRET_KEY` set
- **Playwright CLI not found:** Run `npx playwright-cli` instead
- **Browser fails to launch:** Run `npx playwright install-deps chromium` (rare on Windows)