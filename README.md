# Myth - Personal ATS Job Watcher & Scraper

*This is a personal project tailored exclusively for Abhijeet Singh.*

**Myth** directly probes public Applicant Tracking System (ATS) APIs (Greenhouse, Ashby, Lever, SmartRecruiters, Workday, Amazon Jobs) to catch freshly published engineering and developer roles before they appear on commercial aggregators.

---

## 🎯 Profile Tailoring

Myth is curated specifically for:
* **Level:** 4th-Year Undergraduate / Fresher (0 Years Experience)
* **Domain:** Java Developer, Full-Stack, Backend, Frontend (Java, Spring Boot, React, Node, REST APIs)
* **Target Roles:** Software Development Engineer (SDE / SWE / SDE 1), Associate Software Engineer, Member of Technical Staff (MTS), Graduate Engineer Trainee (GET), Frontend Developer, Backend Developer, Full-Stack Developer, Engineering Intern.
* **Strict Exclusions:** All senior, staff, lead, principal, architect, manager, and multi-year experienced positions (`SDE II`, `SWE 2`, `SMTS`, `LMTS`, `PMTS`, `MTS II/III`, `Level 2+`), as well as non-tech tracks (sales, HR, marketing, UI/UX design, customer support).
* **Strict Freshness Rule:** Only openings posted within the last **24 hours** (`MAX_AGE_HOURS = 24.0`) trigger alerts. Older active roles are filtered out.
* **Zero Duplicates:** Tracks every seen job ID in SQLite (`seen_jobs.db`). A job is only ever notified once and never repeated.
* **Locations:** India (Bengaluru, Hyderabad, Pune, Delhi NCR, Noida, Gurgaon, Chennai, Mumbai, Kolkata, Ahmedabad) & Global Remote / Work-From-Home.

---

## 🚀 How It Works

```mermaid
flowchart LR
    A["Public ATS & Career APIs<br/>(Greenhouse, Ashby, Lever, SmartRecruiters, Workday, Amazon)"] --> B["Myth Filter Engine"]
    B -->|Keywords & Location & <= 24h| C{"Seen in SQLite DB?<br/>(seen_jobs.db)"}
    C -->|Already Seen| D["Skip / Record"]
    C -->|New Match| E["Telegram Bot Alert<br/>(Role, Company, IST Time, Apply Link)"]
```

1. **Direct Public ATS & Career API Polling:** Directly queries public JSON endpoints for Greenhouse, Ashby, Lever, SmartRecruiters, Workday, and Amazon Jobs across 241+ verified boards.
2. **Instant Telegram Alerts:** When a job matches your profile, is $\le$ 24 hours old, and has not been sent before, an HTML-formatted alert is dispatched directly to your Telegram chat with the posting timestamp in IST and direct application link.
3. **Continuous 15-Minute Polling:** Polls all 241 boards in parallel in ~45 seconds, updates `seen_jobs.db`, and alerts you immediately.

---

## 💻 15-Minute Scheduler Execution Options

### Option A: Local Background Daemon on Windows (Recommended - Zero Delays)
Runs continuously on your machine every 15 minutes, independent of cloud queues:
```powershell
.\start_background.ps1    # Starts silent background watcher (every 15 mins)
.\status_watcher.ps1     # Checks daemon status, PID, memory, and recent log output
.\stop_background.ps1      # Stops background watcher
```
To stream live scan logs in your PowerShell console:
```powershell
Get-Content watcher.log -Tail 30 -Wait
```

### Option B: Cloud Automation via GitHub Actions & Webhook
GitHub Actions provides `.github/workflows/job_watcher.yml` to run in the cloud.

> [!NOTE]
> **Why native GitHub Actions cron has delays:** GitHub Actions `schedule: cron` runs on a shared, best-effort queue. During peak global loads, GitHub intentionally batches or skips high-frequency schedules (< 1 hour).
>
> To make GitHub Actions trigger **strictly every 15 minutes without any delays**, use an external webhook caller (like [cron-job.org](https://cron-job.org) - free):
> 1. In GitHub, create a Personal Access Token (PAT) with `repo` or `workflow` scope.
> 2. Create a free 15-minute cron at [cron-job.org](https://cron-job.org):
>    - **URL:** `https://api.github.com/repos/abhijeet-rx/Myth/actions/workflows/job_watcher.yml/dispatches`
>    - **Method:** `POST`
>    - **Headers:**
>      - `Authorization: Bearer <YOUR_GITHUB_PAT>`
>      - `Accept: application/vnd.github.v3+json`
>      - `User-Agent: Myth-Job-Watcher`
>    - **Body:** `{"ref": "main"}`
> 3. cron-job.org triggers GitHub's `workflow_dispatch` API every 15 minutes on the exact second with zero queue dropping!

---

## 🛠️ On-Demand Tools & Commands

### 1. On-Demand Single Company Search
Search any company's job board live across Greenhouse, Ashby, Lever, SmartRecruiters, Workday, and Amazon:
```powershell
# Search Workday giants on-demand (e.g. Salesforce, Nvidia, Adobe)
py search_company.py salesforce --all
py search_company.py nvidia --all
py search_company.py adobe --all

# Search Big Tech (Amazon Jobs)
py search_company.py amazon --all

# Check for fresh openings (< 24 hours old)
py search_company.py stripe

# Include all active openings (regardless of posting age)
py search_company.py stripe --all

# Push matched openings directly to your Telegram
py search_company.py swiggy --send-tg
```

### 2. Preview Current Watchlist Matches (Dry Run)
Inspect all matching roles currently live across all monitored companies without recording to the database:
```powershell
py job_watcher.py --dry-run
```

### 3. Bulk Company Scanner (1,170+ Tech Firms)
Scan the master list of companies ([`company_list.txt`](company_list.txt)) to discover active ATS endpoints:
```powershell
py bulk_scan_companies.py --fresh-only
```

---

## ⚙️ Configuration & Secrets

Myth uses a local `.env` file (never committed to Git) and GitHub Secrets for Telegram bot dispatch:
* `TELEGRAM_BOT_TOKEN`: Telegram bot token from `@BotFather`
* `TELEGRAM_CHAT_ID`: Your personal Telegram chat ID
