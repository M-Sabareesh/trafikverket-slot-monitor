# 🚗 Trafikverket & Volvo Monitors

This repository contains two automated monitors:

1. **Trafikverket Slot Monitor** - Monitors [Trafikverket's booking portal](https://fp.trafikverket.se/Boka/) for available driving test slots
2. **Volvo Lease Monitor** - Monitors [Volvo's employee portal](https://www.volvobil.se/sv/) for lease car availability

## ✨ Features

### Trafikverket Monitor
- 🔍 Monitors **multiple locations** simultaneously for available slots
- 📅 Filter by date (only show slots before a certain date)
- 📧 Email notifications (Gmail, Outlook, etc.)
- 📱 Telegram notifications
- 💬 Discord notifications
- ⏰ Runs automatically via GitHub Actions
- 💾 Remembers previously found slots (no duplicate alerts)

### Volvo Lease Monitor
- 🚗 Monitors Volvo employee portal for lease car options
- 📧 Sends email notification when "Lease Car" option becomes available
- 🏢 Supports VCC Volvo Passenger Cars AB - Gothenburg
- ⏰ Runs on the same schedule as Trafikverket monitor

## 🚀 Quick Start

### 1. Get Your Booking URL

1. Go to [fp.trafikverket.se/Boka/](https://fp.trafikverket.se/Boka/)
2. Log in with **BankID**
3. Navigate to the search page for your test type
4. Copy the URL (looks like `https://fp.trafikverket.se/Boka/ng/search/atIitaeAOChRPr/5/12/0/0`)

### 2. Local Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/trafikverket-slot-monitor.git
cd trafikverket-slot-monitor

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure environment
cp .env.example .env
nano .env  # Edit with your settings

# Run the monitor
python src/main.py
```

### 3. GitHub Actions Setup (Automated Monitoring)

1. Fork/push this repository to GitHub
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Add the following secrets:

| Secret | Description | Required |
|--------|-------------|----------|
| `BOOKING_URL` | Your Trafikverket booking URL | ✅ |
| `LOCATIONS` | Comma-separated locations to search (e.g., `Göteborg-Hisingen,Göteborg Öst`) | ✅ |
| `CHECK_BEFORE_DATE` | Only show slots before this date (YYYY-MM-DD) | ❌ |
| `NOTIFICATION_EMAIL` | Email to receive notifications | ❌ |
| `SMTP_SERVER` | SMTP server (default: smtp.gmail.com) | ❌ |
| `SMTP_PORT` | SMTP port (default: 587) | ❌ |
| `SMTP_USERNAME` | Email address for sending | ❌ |
| `SMTP_PASSWORD` | Email app password | ❌ |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | ❌ |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | ❌ |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL | ❌ |

### Multi-Location Monitoring

The monitor can search **multiple locations** in a single run. Configure this using the `LOCATIONS` environment variable:

```bash
# In your .env file
LOCATIONS=Göteborg-Hisingen,Göteborg Öst

# Or via command line
LOCATIONS="Göteborg-Hisingen,Göteborg Öst" python src/main.py
```

Each location is searched separately, and results are combined (duplicates removed). This is useful when you're flexible about which test center you can go to.

4. The workflow runs automatically every 2 hours during daytime (Stockholm time)

## 📧 Setting Up Notifications

### Email (Gmail)

1. Enable 2-factor authentication on your Google account
2. Create an App Password: [Google App Passwords](https://support.google.com/accounts/answer/185833)
3. Use the App Password in `SMTP_PASSWORD`

### Telegram

1. Create a bot with [@BotFather](https://t.me/botfather)
2. Get your chat ID from [@userinfobot](https://t.me/userinfobot)
3. Start a chat with your bot first

### Discord

1. In Discord, go to Server Settings → Integrations → Webhooks
2. Create a new webhook and copy the URL

## 🛠️ Command Line Options

```bash
python src/main.py                 # Normal run
python src/main.py --dry-run       # Don't send notifications
python src/main.py --debug         # Save screenshots for debugging
python src/main.py --force-notify  # Test notifications
```

## 📁 Project Structure

```
trafikverket-slot-monitor/
├── src/
│   ├── main.py          # Entry point
│   ├── config.py        # Configuration
│   ├── scraper.py       # Web scraping logic (Playwright)
│   ├── monitor.py       # Legacy monitor class
│   └── notifier.py      # Notification handlers
├── tests/               # Unit tests
├── data/                # Runtime data (gitignored)
├── .github/workflows/   # GitHub Actions
├── .env.example         # Example configuration
├── requirements.txt     # Python dependencies
└── README.md
```

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `playwright not found` | Run `playwright install chromium` |
| `No slots found` | Check `data/current_state.png` screenshot |
| `Email not sending` | For Gmail, use [App Password](https://support.google.com/accounts/answer/185833) |
| `Session expired` | Log into Trafikverket again and update `BOOKING_URL` |

## ⚠️ Important Notes

1. **The booking URL contains your session** - it's tied to your BankID login
2. **Session may expire** - you might need to refresh the URL periodically
3. **Don't share your booking URL** - it contains personal information
4. **Respect rate limits** - don't run too frequently

## ⏰ Scheduling Reliability

**Note:** GitHub Actions scheduled workflows are NOT guaranteed to run on time. During periods of high load, scheduled workflows may be delayed by minutes or even hours. The runs you see may be hours apart instead of every 5 minutes.

### Options for More Reliable Scheduling

#### Option 1: Run Locally (Most Reliable)
```bash
# Run continuously with 60-second intervals
python src/main.py --loop --always-notify
```

#### Option 2: Use External Trigger Service
Use a service like [cron-job.org](https://cron-job.org) to trigger the workflow via the GitHub API:

1. Create a GitHub Personal Access Token with `repo` scope
2. Set up a cron job to call:
   ```bash
   curl -X POST \
     -H "Authorization: token YOUR_GH_PAT" \
     -H "Accept: application/vnd.github.v3+json" \
     https://api.github.com/repos/YOUR_USER/trafikverket-slot-monitor/dispatches \
     -d '{"event_type":"trigger-monitor"}'
   ```
3. Schedule it to run every 5 minutes

---

## 🚗 Volvo Lease Monitor

### Setup

1. **First-time login** (requires browser):
   ```bash
   python src/volvo_monitor.py --login
   ```
   This will open a browser where you can log in to the Volvo portal.

2. **Save session to GitHub** (for automated runs):
   ```bash
   # Encode and save the session
   base64 -w 0 data/volvo/volvo_session.json | gh secret set VOLVO_SESSION_DATA
   ```

3. **Run manually**:
   ```bash
   python src/volvo_monitor.py --debug
   ```

### How it works

The monitor:
1. Goes to https://www.volvobil.se/sv/
2. Logs in using saved session
3. Navigates to Order section
4. Selects "VCC Volvo Passenger Cars AB - Gothenburg"
5. Selects brand "Volvo"
6. Selects "New assignment"
7. Checks if "Lease Car" option is available
8. Sends email notification if lease option is found

### Command Line Options

```bash
python src/volvo_monitor.py                # Normal run (headless)
python src/volvo_monitor.py --login        # Interactive login
python src/volvo_monitor.py --dry-run      # Don't send notifications  
python src/volvo_monitor.py --debug        # Save screenshots for debugging
```

### Running Both Monitors

To trigger both monitors with one cron job, use the `trigger-all-monitors` event:
```bash
curl -X POST \
  -H "Authorization: token YOUR_GH_PAT" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/YOUR_USER/trafikverket-slot-monitor/dispatches \
  -d '{"event_type":"trigger-all-monitors"}'
```