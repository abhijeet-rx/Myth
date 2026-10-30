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
import re
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
    # General engineering titles freshers/colleges get hired for
    "software engineer",
    "software developer",
    "sde",
    "swe",
    "programmer",
    "developer",
    "engineer",
    "member of technical staff",
    "mts",
    # Specific tech stack: Java / Full Stack / Frontend / Backend / Web
    "java",
    "full stack",
    "full-stack",
    "fullstack",
    "backend",
    "back end",
    "back-end",
    "frontend",
    "front end",
    "front-end",
    "web developer",
    "react",
    "node",
    "spring",
    "springboot",
    # Entry-level / Fresher / College campus specifics
    "intern",
    "internship",
    "new grad",
    "graduate",
    "entry level",
    "entry-level",
    "early career",
    "campus",
    "fresher",
    "trainee",
    "apprentice",
    "associate engineer",
    "associate software",
    "associate developer",
    "junior",
    "jr.",
    "jr ",
    "sde 1",
    "sde i",
    "sde-1",
    "sde-i",
    "swe 1",
    "swe i",
    "swe-1",
    "swe-i",
    "engineer 1",
    "engineer i",
]

EXCLUDE = [
    # Seniority & Experienced levels (strictly excluded for 0-exp / fresher)
    "senior",
    "sr.",
    "sr ",
    "sr-",
    "staff",
    "principal",
    "lead",
    "tech lead",
    "team lead",
    "architect",
    "director",
    "manager",
    "head of",
    "vp",
    "vice president",
    "fellow",
    "distinguished",
    "expert",
    "sde ii",
    "sde-ii",
    "sde 2",
    "sde-2",
    "sde iii",
    "sde-3",
    "sde 3",
    "sde iv",
    "swe ii",
    "swe-ii",
    "swe 2",
    "swe-2",
    "swe iii",
    "software engineer ii",
    "software engineer 2",
    "software engineer iii",
    "software engineer 3",
    "engineer ii",
    "engineer 2",
    "engineer iii",
    "engineer 3",
    "mid-level",
    "mid level",
    "experienced",
    # Non-software engineering disciplines
    "mechanical",
    "electrical",
    "civil",
    "chemical",
    "hardware",
    "network engineer",
    # Non-tech / Unrelated tracks
    "sales",
    "account executive",
    "recruiter",
    "sourcer",
    "talent acquisition",
    "marketing",
    "legal",
    "operations",
    "finance",
    "accounting",
    "product manager",
    "designer",
    "ui/ux",
    "content",
    "hr ",
    "human resources",
    "business analyst",
    "customer support",
    "technical support",
    "help desk",
    "helpdesk",
]

# Whole-word token exclusions to catch "Sr", "II", "Lead", "Analytics", etc. accurately
EXCLUDE_WORDS = {
    "senior",
    "sr",
    "staff",
    "principal",
    "lead",
    "director",
    "manager",
    "vp",
    "architect",
    "fellow",
    "expert",
    "ii",
    "iii",
    "iv",
    "experienced",
    "mechanical",
    "electrical",
    "civil",
    "chemical",
    "hardware",
    "sales",
    "recruiter",
    "sourcer",
    "marketing",
    "legal",
    "finance",
    "accounting",
    "designer",
    "analytics",
    "analyst",
    "scrum",
    "hr",
    "auditor",
    "audit",
    "compliance",
    "tax",
}

LOCATIONS = [
    "india",
    "bengaluru",
    "bangalore",
    "hyderabad",
    "pune",
    "delhi",
    "noida",
    "gurgaon",
    "gurugram",
    "chennai",
    "mumbai",
    "ahmedabad",
    "kolkata",
    "remote",
    "anywhere",
    "work from home",
]

MAX_AGE_HOURS = 24.0  # STRICT RULE: Throw out any jobs older than 24 hours

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
            if results:
                return "Greenhouse", results
    except Exception:
        pass

    # 2. Try Ashby
    results = []
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
            if results:
                return "Ashby", results
    except Exception:
        pass

    # 3. Try Lever
    results = []
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
            if results:
                return "Lever", results
    except Exception:
        pass

    # 4. Try SmartRecruiters
    results = []
    sr_url = f"https://api.smartrecruiters.com/v1/companies/{slug_clean}/postings"
    try:
        r = requests.get(sr_url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json().get("content", [])
            if data:
                for j in data:
                    loc_obj = j.get("location") or {}
                    loc_parts = [p for p in [loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country")] if p]
                    loc = ", ".join(loc_parts) or "Unspecified"
                    if loc_obj.get("remote"):
                        loc = f"{loc} (Remote)".strip()
                    hrs, t_str = parse_timing(j.get("releasedDate"))
                    results.append({
                        "source": "SmartRecruiters",
                        "company": slug.title(),
                        "title": (j.get("name") or "").strip(),
                        "location": loc,
                        "url": f"https://jobs.smartrecruiters.com/{slug_clean}/{j.get('id')}" if j.get("id") else "",
                        "age_hours": hrs,
                        "timing_str": t_str,
                    })
                if results:
                    return "SmartRecruiters", results
    except Exception:
        pass

    return None, []

def main():
    parser = argparse.ArgumentParser(description="Search any company's job openings")
    parser.add_argument("company", help="Company name or slug (e.g. stripe, openai, swiggy, rubrik)")
    parser.add_argument("--all", action="store_true", help="Include active jobs older than 6 hours")
    parser.add_argument("--send-tg", action="store_true", help="Send matches directly to Telegram bot")
    args = parser.parse_args()

    print(f"[*] Probing job boards for '{args.company}'...")
    platform, all_jobs = fetch_company_jobs(args.company)

    if not platform:
        print(f"[-] Could not find a public Greenhouse, Ashby, Lever, or SmartRecruiters board for '{args.company}'.")
        print("    (Some companies use custom portals or different career slug names).")
        return

    print(f"[+] Found board on {platform}! Total active postings: {len(all_jobs)}")

    # Filter by profile
    matched = []
    for j in all_jobs:
        t = j["title"].lower()
        loc = j["location"].lower()

        # 1. Whole-word and phrase exclusions for 0-exp fresher
        words = set(re.findall(r"[a-zA-Z0-9]+", t))
        if words.intersection(EXCLUDE_WORDS):
            continue
        if any(x in t for x in EXCLUDE):
            continue
        # 2. Tech stack and target roles
        if not any(k in t for k in KEYWORDS):
            continue
        # 3. Location filter
        if LOCATIONS and not any(l in loc for l in LOCATIONS):
            continue
        
        # STRICT 6-HOUR RULE: Throw out all jobs older than 6 hours (unless --all is specified)
        if not args.all:
            if j["age_hours"] is None or j["age_hours"] > MAX_AGE_HOURS or j["age_hours"] < -2.0:
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
