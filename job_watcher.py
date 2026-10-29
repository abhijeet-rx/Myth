#!/usr/bin/env python3
"""
job_watcher.py - Poll public ATS job-board APIs and alert on NEW postings via Telegram.

Curated for Abhijeet Singh:
  - Focus: Full-Stack, Backend, Frontend, Java Developer, SDE, Intern, New Grad
  - Tracks: Greenhouse, Ashby, Lever
  - Alerts: Telegram Bot with IST Timings

Setup:
  1. Create a bot with @BotFather on Telegram -> TELEGRAM_BOT_TOKEN
  2. Send a message to your bot, then open:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     to find your "chat": {"id": ...} -> TELEGRAM_CHAT_ID
  3. Set environment variables:
     $env:TELEGRAM_BOT_TOKEN="your_token"
     $env:TELEGRAM_CHAT_ID="your_chat_id"

Usage:
  py job_watcher.py               # Runs daemon loop every POLL_SECONDS
  py job_watcher.py --once        # Runs a single pass and exits
  py job_watcher.py --dry-run     # Inspect all current active matching jobs without DB writes
"""
import argparse
import datetime
import os
import sqlite3
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests

# ---- CONFIG: Curated for Abhijeet Singh ----
COMPANIES = {
    "greenhouse": [
        "stripe",
        "airbnb",
        "razorpaysoftwareprivatelimited",
        "rubrik",
        "gitlab",
        "databricks",
        "cloudflare",
        "elastic",
        "samsara",
        "mongodb",
        "figma",
        "brex",
        "affirm",
    ],
    "ashby": [
        "openai",
        "notion",
        "ramp",
        "perplexity",
        "modal",
        "cursor",
        "linear",
    ],
    "lever": [
        "palantir",
        "spotify",
    ],
}

KEYWORDS = [
    "software engineer",
    "software developer",
    "sde",
    "backend",
    "back end",
    "front end",
    "frontend",
    "full stack",
    "full-stack",
    "fullstack",
    "java",
    "intern",
    "internship",
    "new grad",
    "early career",
    "trainee",
]

EXCLUDE = [
    "senior",
    "sr.",
    "sr ",
    "staff",
    "principal",
    "manager",
    "director",
    "lead",
    "vp",
    "head of",
    "architect",
    "sales",
    "account executive",
    "recruiter",
    "sourcer",
    "marketing",
    "legal",
    "operations",
    "analyst",
    "product manager",
    "designer",
]

LOCATIONS = [
    "india",
    "bengaluru",
    "bangalore",
    "hyderabad",
    "pune",
    "remote",
]  # lowercase substrings; leave empty [] for any location

MAX_AGE_HOURS = 24.0  # Only alert on postings <= 24 hours old
POLL_SECONDS = 1800   # Scan every 30 minutes (30m * 60s)
DB_PATH = "seen_jobs.db"
# --------------------------------------------------------------------------

def load_env(path=".env"):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k not in os.environ and v:
                        os.environ[k] = v

load_env()

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
HEADERS = {"User-Agent": "job-watcher/1.0 (personal career researcher)"}
IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def parse_datetime(val):
    if not val:
        return None
    try:
        if isinstance(val, (int, float)):
            # Epoch milliseconds (common in Lever)
            return datetime.datetime.fromtimestamp(val / 1000.0, tz=datetime.timezone.utc)
        if isinstance(val, str):
            dt = datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    return None


def format_timing(dt):
    if not dt:
        return "Unknown"
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    delta = now_utc - dt
    total_seconds = max(0, delta.total_seconds())
    minutes = int(total_seconds // 60)
    hours = total_seconds / 3600.0
    days = int(total_seconds // 86400)

    if minutes < 60:
        rel = f"{minutes} min{'s' if minutes != 1 else ''} ago"
    elif hours < 24:
        rel = f"{hours:.1f} hours ago"
    else:
        rel = f"{days} day{'s' if days != 1 else ''} ago"

    ist_time = dt.astimezone(IST_TZ).strftime("%d %b, %I:%M %p IST")
    return f"{rel} ({ist_time})"


def fetch_greenhouse(slug):
    r = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        dt = parse_datetime(j.get("first_published") or j.get("updated_at"))
        yield {
            "id": f"gh:{slug}:{j['id']}",
            "title": (j.get("title") or "").strip(),
            "location": ((j.get("location") or {}).get("name") or "").strip(),
            "url": j.get("absolute_url", ""),
            "company": slug.replace("softwareprivatelimited", "").title(),
            "source": "Greenhouse",
            "posted_at": dt,
            "timing_str": format_timing(dt),
        }


def fetch_lever(slug):
    r = requests.get(
        f"https://api.lever.co/v0/postings/{slug}",
        params={"mode": "json"},
        headers=HEADERS,
        timeout=25,
    )
    r.raise_for_status()
    for j in r.json():
        loc = (j.get("categories") or {}).get("location", "") or ""
        dt = parse_datetime(j.get("createdAt"))
        yield {
            "id": f"lv:{slug}:{j['id']}",
            "title": (j.get("text") or "").strip(),
            "location": loc.strip(),
            "url": j.get("hostedUrl", ""),
            "company": slug.title(),
            "source": "Lever",
            "posted_at": dt,
            "timing_str": format_timing(dt),
        }


def fetch_ashby(slug):
    r = requests.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        loc = (j.get("location") or "").strip()
        if j.get("isRemote") and "remote" not in loc.lower():
            loc = f"{loc} (Remote)".strip() if loc else "Remote"
        dt = parse_datetime(j.get("publishedAt"))
        yield {
            "id": f"ab:{slug}:{j['id']}",
            "title": (j.get("title") or "").strip(),
            "location": loc,
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "company": slug.title(),
            "source": "Ashby",
            "posted_at": dt,
            "timing_str": format_timing(dt),
        }


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def matches(job, enforce_max_age=True):
    title = job["title"].lower()
    loc = job["location"].lower()
    if any(x in title for x in EXCLUDE):
        return False
    if not any(k in title for k in KEYWORDS):
        return False
    if LOCATIONS and not any(l in loc for l in LOCATIONS):
        return False
    
    # Strictly reject any job older than 24 hours
    if enforce_max_age and job.get("posted_at"):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        age_hours = (now_utc - job["posted_at"]).total_seconds() / 3600.0
        if age_hours > MAX_AGE_HOURS:
            return False

    return True


def notify(job, dry_run=False):
    text = (
        f"🎯 [New Job Match]\n"
        f"Role: {job['title']}\n"
        f"Company: {job['company']} ({job['source']})\n"
        f"Location: {job['location'] or 'Unspecified'}\n"
        f"Posted: {job['timing_str']}\n"
        f"Link: {job['url']}"
    )
    print(f"\n{text}\n")
    if dry_run:
        return

    if not (TG_TOKEN and TG_CHAT):
        return

    tg_html = (
        f"🎯 <b>New Job Match</b>\n\n"
        f"<b>Role:</b> {job['title']}\n"
        f"<b>Company:</b> {job['company']} ({job['source']})\n"
        f"<b>Location:</b> {job['location'] or 'Unspecified'}\n"
        f"<b>Posted:</b> {job['timing_str']}\n\n"
        f"🔗 <a href='{job['url']}'><b>Apply on Career Page</b></a>"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT,
                "text": tg_html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except Exception as e:
        print(f"[warn] Failed to send Telegram alert: {e}", file=sys.stderr)


def poll_cycle(db, dry_run=False):
    total_found = 0
    all_matched = []

    for source, slugs in COMPANIES.items():
        fetcher = FETCHERS.get(source)
        if not fetcher:
            continue

        for slug in slugs:
            print(f"[{source}] Polling '{slug}'...", end=" ", flush=True)
            try:
                jobs = list(fetcher(slug))
                total_found += len(jobs)
                print(f"{len(jobs)} active jobs found.", flush=True)
            except Exception as e:
                print(f"FAILED: {e}", flush=True)
                continue

            seeded = False
            if db:
                row = db.execute(
                    "SELECT 1 FROM seen WHERE company=? LIMIT 1", (slug,)
                ).fetchone()
                seeded = row is not None

            new_in_company = 0
            for job in jobs:
                if dry_run:
                    if matches(job):
                        all_matched.append(job)
                    continue

                is_new = not db.execute(
                    "SELECT 1 FROM seen WHERE id=?", (job["id"],)
                ).fetchone()
                if not is_new:
                    continue

                new_in_company += 1
                db.execute(
                    "INSERT INTO seen VALUES (?, ?, ?)",
                    (job["id"], slug, time.time()),
                )

                if seeded and matches(job):
                    all_matched.append(job)
                    notify(job, dry_run=False)

            if not dry_run:
                db.commit()
                if not seeded:
                    print(f"  └─ First run for '{slug}': seeded {len(jobs)} jobs silently.")
                elif new_in_company > 0:
                    print(f"  └─ Found {new_in_company} new listings.")

            time.sleep(1)

    if dry_run:
        all_matched.sort(
            key=lambda x: x["posted_at"].timestamp() if x.get("posted_at") else 0,
            reverse=True,
        )
        print(f"\n==================================================")
        print(f"TOTAL MATCHES FOUND: {len(all_matched)} (Sorted by newest first)")
        print(f"==================================================")
        for job in all_matched:
            notify(job, dry_run=True)

    return total_found, len(all_matched)


def main():
    parser = argparse.ArgumentParser(description="ATS Job Watcher daemon (Telegram Edition)")
    parser.add_argument("--once", action="store_true", help="Run one poll pass and exit")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect all current active matching jobs with timings without writing to DB",
    )
    args = parser.parse_args()

    db = None
    if not args.dry_run:
        db = sqlite3.connect(DB_PATH)
        db.execute(
            "CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, company TEXT, first_seen REAL)"
        )
        db.commit()

    print("=== ATS Job Watcher Started (Telegram Alerts) ===")
    print(f"Target Keywords: {KEYWORDS[:6]}...")
    print(f"Locations:       {LOCATIONS or 'All'}")
    print(f"Mode:            {'Dry Run (View All Available)' if args.dry_run else 'Single pass' if args.once else f'Loop ({POLL_SECONDS}s)'}")
    if TG_TOKEN and TG_CHAT:
        print(f"Telegram Bot:    Configured (Chat ID: {TG_CHAT})")
    else:
        print("Telegram Bot:    Not configured (alerts will only print to console)")
    print("=================================================\n")

    try:
        while True:
            poll_cycle(db, dry_run=args.dry_run)
            if args.once or args.dry_run:
                break
            print(f"\nSleeping for {POLL_SECONDS} seconds...\n")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nJob Watcher stopped by user.")
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    main()
