# Myth - Automated ATS Job Watcher & Telegram Dispatcher

An intelligent, real-time job monitoring daemon that directly polls public Applicant Tracking System (ATS) APIs (**Greenhouse**, **Ashby**, **Lever**) and dispatches alerts directly to Telegram with exact IST publication timestamps and direct apply links.

## 🚀 Features

- **Direct ATS Integration**: Polls source boards directly (skips rate-limited/scraped syndication sites).
- **Curated Stack Filtering**: Specifically tuned for **Full-Stack, Backend, Frontend, Java Developer, SDE, Intern, and New Grad** positions.
- **Strict Exclusions**: Automatically weeds out Senior, Staff, Principal, Lead, and non-engineering roles.
- **24-Hour Freshness Filter**: Rejects stale jobs older than 24 hours.
- **24/7 Automated Scheduling**: Built-in GitHub Actions workflow running on a 30-minute cron cycle.
- **On-Demand Search**: Probe any company's ATS board instantly with `py search_company.py <company>`.

---

## 🛠️ Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/abhijeet-rx/Myth.git
   cd Myth
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables** (or create a `.env` file):
   ```env
   TELEGRAM_BOT_TOKEN="your_bot_token"
   TELEGRAM_CHAT_ID="your_chat_id"
   ```

---

## 💻 Usage

### 1. Run Continuous Watcher (Every 30 Mins)
```bash
python job_watcher.py
```

### 2. Run Single Pass (Ideal for Cron/CI)
```bash
python job_watcher.py --once
```

### 3. Dry Run (Inspect Active Jobs Without Alerting)
```bash
python job_watcher.py --dry-run
```

### 4. Search Any Company On-Demand
```bash
# Check roles posted in the last 24h
python search_company.py stripe

# Push findings to your Telegram
python search_company.py openai --send-tg

# Search all active postings (including older ones)
python search_company.py gitlab --all
```

---

## ☁️ 24/7 GitHub Actions Setup

To run this 24/7 in the cloud for free without keeping your computer on:

1. Push this repository to GitHub.
2. In your GitHub repo, navigate to:
   **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
3. Add the two secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. The workflow in [`.github/workflows/job_watcher.yml`](.github/workflows/job_watcher.yml) will automatically run every **30 minutes**.
