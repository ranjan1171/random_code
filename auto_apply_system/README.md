# Auto Job Apply System

A fully automated job application engine for **Ranjan Kumar**. Scrapes multiple portals,
matches jobs to your profile using AI, and submits applications — all without you opening a browser.

## Features

| Feature | Details |
|---------|---------|
| 🔍 **Multi-portal scraping** | LinkedIn, Naukri, Indeed, Wellfound, Internshala, Freehire.dev |
| 🤖 **AI matching** | TF-IDF cosine similarity + rule-based scoring (0–100%) |
| 🖱️ **Browser automation** | Playwright + stealth mode (anti-bot detection bypass) |
| 🧩 **CAPTCHA handling** | CapSolver API + 2Captcha fallback + evasion-first |
| 📧 **Email monitoring** | Gmail IMAP — detects OTPs, confirmations, interview invites |
| 📊 **Dashboard** | Real-time web UI at http://localhost:5000 |
| 💾 **SQLite tracking** | Every job scraped, every application sent, every email received |

## Quick Start

```powershell
# 1. Setup (installs everything)
cd auto_apply_system
python setup.py

# 2. Edit .env with your credentials
notepad .env

# 3. Test everything works
python main.py --test

# 4. Dry run (scrape without applying)
python main.py --dry-run

# 5. Full system
python main.py
```

## Dashboard

Open **http://localhost:5000** after starting the system.

## Commands

| Command | Description |
|---------|-------------|
| `python main.py` | Full system (scrape + match + apply + dashboard) |
| `python main.py --dry-run` | Scrape & score — no applications submitted |
| `python main.py --test` | Test all components (scrapers, DB, Playwright, email) |
| `python main.py --dashboard` | Dashboard only (view existing data) |
| `python main.py --no-dashboard` | Run without opening dashboard |

## Profile

Built for **Ranjan Kumar** (edit `config.py` to change):
- **Skills**: Python, Kafka, Rust, C++, Node.js, Distributed Systems
- **Targets**: FinTech, HFT, Backend Engineering in Pune/Bangalore/Remote
- **Min match score**: 60% (configurable in `.env`)

## Architecture

```
main.py (Orchestrator)
├── scrapers/        LinkedIn · Naukri · Indeed · Wellfound · Internshala · Freehire
├── matcher/         TF-IDF scoring against Ranjan's profile
├── applier/         Playwright browser automation per portal
├── captcha/         CapSolver + 2Captcha + stealth evasion
├── email_monitor/   Gmail IMAP — OTP + confirmation detection
├── db/              SQLite — jobs, applications, emails
└── dashboard/       Flask + Vanilla JS real-time UI
```

## Configuration

All settings in `.env`:

```
# Portal passwords
LINKEDIN_PASSWORD=...
NAUKRI_PASSWORD=...

# CAPTCHA (optional)
CAPSOLVER_API_KEY=...

# Gmail monitoring (optional)
GMAIL_APP_PASSWORD=...

# Tuning
MIN_MATCH_SCORE=60
MAX_DAILY_APPLICATIONS=20
HEADLESS_BROWSER=false
```

## Legal Notice

This tool is for personal use only. Automated access to job portals may violate their Terms of Service.
Keep application volume low and use responsibly.
