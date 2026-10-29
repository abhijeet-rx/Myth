#!/usr/bin/env python3
"""
search_company.py - Look up live job openings for any company on-demand.

Usage:
  py search_company.py <company_name_or_slug>
  py search_company.py <company_name_or_slug> --send-tg    # Push matches to your Telegram
  py search_company.py <company_name_or_slug> --all        # Include older active postings
"""
import argparse
import datetime
import os
import sys
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load .env
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
IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
HEADERS = {"User-Agent": "job-watcher/1.0 (personal career researcher)"}

KEYWORDS = [
    "software engineer", "software developer", "sde", "backend", "back end",
    "front end", "frontend", "full stack", "full-stack", "fullstack",
    "java", "intern", "internship", "new grad", "early career", "trainee"
]

EXCLUDE = [
    "senior", "sr.", "sr ", "staff", "principal", "manager", "director",
    "lead", "vp", "head of", "architect", "sales", "account executive",
    "recruiter", "sourcer", "marketing", "legal", "operations", "analyst",
    "product manager", "designer"
]

LOCATIONS = ["india", "bengaluru", "bangalore", "hyderabad", "pune", "remote"]

def parse_timing(dt_val):
    if not dt_val:
        return None, "Active Opening"
    try:
        if isinstance(dt_val, (int, float)):
            dt = datetime.datetime.fromtimestamp(dt_val / 1000.0, tz=datetime.timezone.utc)
        else:
            dt = datetime.datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            dt = dt.astimezone(datetime.timezone.utc)

        now = datetime.datetime.now(datetime.timezone.utc)
        hrs = (now - dt).total_seconds() / 3600.0
        if hrs < 24:
            rel = f"{hrs:.1f} hrs ago"
        else:
            rel = f"{int((now - dt).days)} days ago"
        ist_str = dt.astimezone(IST_TZ).strftime("%d %b, %I:%M %p IST")
        return hrs, f"{rel} ({ist_str})"
    except Exception:
        return None, "Active Opening"

def fetch_company_jobs(slug):
    slug_clean = slug.strip().lower().replace(" ", "")
    results = []

    # 1. Try Greenhouse
    gh_url = f"https://boards-api.greenhouse.io/v1/boards/{slug_clean}/jobs"
    try:
        r = requests.get(gh_url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            for j in r.json().get("jobs", []):
                hrs, t_str = parse_timing(j.get("first_published") or j.get("updated_at"))
                results.append({
                    "source": "Greenhouse",
                    "company": slug.title(),
                    "title": (j.get("title") or "").strip(),
                    "location": ((j.get("location") or {}).get("name") or "Unspecified").strip(),
                    "url": j.get("absolute_url", ""),
                    "age_hours": hrs,
                    "timing_str": t_str,
                })
            return "Greenhouse", results
    except Exception:
        pass

    # 2. Try Ashby
    ab_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug_clean}"
    try:
        r = requests.get(ab_url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            for j in r.json().get("jobs", []):
                loc = (j.get("location") or "").strip()
                if j.get("isRemote") and "remote" not in loc.lower():
                    loc = f"{loc} (Remote)".strip() if loc else "Remote"
                hrs, t_str = parse_timing(j.get("publishedAt"))
                results.append({
                    "source": "Ashby",
                    "company": slug.title(),
                    "title": (j.get("title") or "").strip(),
                    "location": loc or "Unspecified",
                    "url": j.get("jobUrl") or j.get("applyUrl") or "",
                    "age_hours": hrs,
                    "timing_str": t_str,
                })
            return "Ashby", results
    except Exception:
        pass

    # 3. Try Lever
    lv_url = f"https://api.lever.co/v0/postings/{slug_clean}?mode=json"
    try:
        r = requests.get(lv_url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            for j in r.json():
                loc = (j.get("categories") or {}).get("location", "") or ""
                hrs, t_str = parse_timing(j.get("createdAt"))
                results.append({
                    "source": "Lever",
                    "company": slug.title(),
                    "title": (j.get("text") or "").strip(),
                    "location": loc.strip() or "Unspecified",
                    "url": j.get("hostedUrl", ""),
                    "age_hours": hrs,
                    "timing_str": t_str,
                })
            return "Lever", results
    except Exception:
        pass

    return None, []

def main():
    parser = argparse.ArgumentParser(description="Search any company's job openings")
    parser.add_argument("company", help="Company name or slug (e.g. stripe, openai, swiggy, rubrik)")
    parser.add_argument("--all", action="store_true", help="Include active jobs older than 24h")
    parser.add_argument("--send-tg", action="store_true", help="Send matches directly to Telegram bot")
    args = parser.parse_args()

    print(f"[*] Probing job boards for '{args.company}'...")
    platform, all_jobs = fetch_company_jobs(args.company)

    if not platform:
        print(f"[-] Could not find a public Greenhouse, Ashby, or Lever board for '{args.company}'.")
        print("    (Some companies use custom portals or different career slug names).")
        return

    print(f"[+] Found board on {platform}! Total active postings: {len(all_jobs)}")

    # Filter by profile
    matched = []
    for j in all_jobs:
        t = j["title"].lower()
        loc = j["location"].lower()

        if any(x in t for x in EXCLUDE):
            continue
        if not any(k in t for k in KEYWORDS):
            continue
        if LOCATIONS and not any(l in loc for l in LOCATIONS):
            continue
        
        # Check 24 hour threshold unless --all is specified
        if not args.all:
            if j["age_hours"] is not None and j["age_hours"] > 24.0:
                continue

        matched.append(j)

    matched.sort(key=lambda x: x["age_hours"] if x["age_hours"] is not None else 999)

    print(f"\n=======================================================")
    print(f"MATCHES FOR ABHIJEET ({'All Active' if args.all else '< 24 Hours Old'}): {len(matched)}")
    print(f"=======================================================\n")

    for idx, job in enumerate(matched, 1):
        print(f"[{idx}] {job['title']} @ {job['company']}")
        print(f"    Location: {job['location']}")
        print(f"    Posted:   {job['timing_str']}")
        print(f"    Link:     {job['url']}\n")

        if args.send_tg and TG_TOKEN and TG_CHAT:
            tg_html = (
                f"🎯 <b>Company Search: {job['company']}</b>\n\n"
                f"<b>Role:</b> {job['title']}\n"
                f"<b>Location:</b> {job['location']}\n"
                f"<b>Posted:</b> {job['timing_str']}\n\n"
                f"🔗 <a href='{job['url']}'><b>Apply on Career Page</b></a>"
            )
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": TG_CHAT, "text": tg_html, "parse_mode": "HTML"},
                    timeout=10,
                )
            except Exception:
                pass

if __name__ == "__main__":
    main()
