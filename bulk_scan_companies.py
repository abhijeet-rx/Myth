#!/usr/bin/env python3
"""
bulk_scan_companies.py - Probe ATS job boards for an input list of companies
and extract matching tech/engineering job postings.

Platforms probed:
  - Greenhouse
  - Ashby
  - Lever
  - Workable
  - SmartRecruiters

Usage:
  py bulk_scan_companies.py                         # Scan companies in company_list.txt
  py bulk_scan_companies.py --input my_list.txt     # Custom file
  py bulk_scan_companies.py --all-locations         # Include all global locations (not just India/Remote)
  py bulk_scan_companies.py --fresh-only            # Jobs posted within last 7 days only
  py bulk_scan_companies.py --max-workers 20        # Thread count
"""

import argparse
import datetime
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

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

INDIA_LOCATIONS = [
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "delhi", "noida",
    "gurgaon", "gurugram", "chennai", "mumbai", "ahmedabad", "kolkata",
    "remote", "anywhere", "work from home"
]

def parse_timing(dt_val):
    if not dt_val:
        return None, "Active Opening"
    try:
        if isinstance(dt_val, (int, float)):
            # Check if in milliseconds or seconds
            if dt_val > 1e11:
                dt = datetime.datetime.fromtimestamp(dt_val / 1000.0, tz=datetime.timezone.utc)
            else:
                dt = datetime.datetime.fromtimestamp(dt_val, tz=datetime.timezone.utc)
        else:
            s = str(dt_val).replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            dt = dt.astimezone(datetime.timezone.utc)

        now = datetime.datetime.now(datetime.timezone.utc)
        hrs = (now - dt).total_seconds() / 3600.0
        days = hrs / 24.0
        if hrs < 24:
            rel = f"{hrs:.1f} hrs ago"
        elif days < 30:
            rel = f"{int(days)}d ago"
        else:
            rel = f"{int(days//30)}mo ago"
        ist_str = dt.astimezone(IST_TZ).strftime("%d %b, %I:%M %p IST")
        return hrs, f"{rel} ({ist_str})"
    except Exception:
        return None, "Active Opening"

def clean_company_name(name):
    clean = re.sub(r'\(.*?\)', '', name)
    clean = re.sub(r'[\u2010-\u2015\-\u2013\u2014]', ' ', clean)
    clean = re.sub(r'\b(Ltd|Pvt|Inc|Corp|Corporation|LLC|SE|plc|AG|Group|Technologies|Technology|Services|Holdings|Solutions|Consulting|Digital)\b\.?', '', clean, flags=re.I)
    clean = ' '.join(clean.split()).strip()
    return clean

def generate_slug_candidates(name):
    cleaned = clean_company_name(name)
    raw_cleaned = re.sub(r'\(.*?\)', '', name).strip()
    candidates = []

    # 1. Cleaned alphanumeric
    c1 = re.sub(r'[^a-zA-Z0-9]', '', cleaned).lower()
    if c1 and len(c1) >= 3:
        candidates.append(c1)

    # 2. Raw name alphanumeric
    c2 = re.sub(r'[^a-zA-Z0-9]', '', raw_cleaned).lower()
    if c2 and len(c2) >= 3 and c2 not in candidates:
        candidates.append(c2)

    # 3. Cleaned hyphenated
    c3 = re.sub(r'[^a-zA-Z0-9]+', '-', cleaned).strip('-').lower()
    if c3 and len(c3) >= 3 and c3 not in candidates:
        candidates.append(c3)

    # 4. First word if multiple words
    words = cleaned.split()
    if len(words) > 1 and len(words[0]) >= 3:
        first = words[0].lower()
        if first not in candidates and first not in ["tata", "the", "global"]:
            candidates.append(first)

    return candidates

def probe_greenhouse(slug, display_name):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            if jobs:
                res = []
                for j in jobs:
                    hrs, t_str = parse_timing(j.get("first_published") or j.get("updated_at"))
                    res.append({
                        "platform": "Greenhouse",
                        "company": display_name,
                        "board_slug": slug,
                        "title": (j.get("title") or "").strip(),
                        "location": ((j.get("location") or {}).get("name") or "Unspecified").strip(),
                        "url": j.get("absolute_url") or "",
                        "age_hours": hrs,
                        "timing_str": t_str,
                    })
                return res
    except Exception:
        pass
    return None

def probe_ashby(slug, display_name):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            if jobs:
                res = []
                for j in jobs:
                    loc = (j.get("location") or "").strip()
                    if j.get("isRemote") and "remote" not in loc.lower():
                        loc = f"{loc} (Remote)".strip() if loc else "Remote"
                    hrs, t_str = parse_timing(j.get("publishedAt"))
                    res.append({
                        "platform": "Ashby",
                        "company": display_name,
                        "board_slug": slug,
                        "title": (j.get("title") or "").strip(),
                        "location": loc or "Unspecified",
                        "url": j.get("jobUrl") or j.get("applyUrl") or "",
                        "age_hours": hrs,
                        "timing_str": t_str,
                    })
                return res
    except Exception:
        pass
    return None

def probe_lever(slug, display_name):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=7)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                res = []
                for j in data:
                    loc = (j.get("categories") or {}).get("location", "") or ""
                    workplace = (j.get("categories") or {}).get("workplaceType", "")
                    if workplace and "remote" in workplace.lower() and "remote" not in loc.lower():
                        loc = f"{loc} ({workplace})".strip() if loc else workplace
                    hrs, t_str = parse_timing(j.get("createdAt"))
                    res.append({
                        "platform": "Lever",
                        "company": display_name,
                        "board_slug": slug,
                        "title": (j.get("text") or "").strip(),
                        "location": loc.strip() or "Unspecified",
                        "url": j.get("hostedUrl") or j.get("applyUrl") or "",
                        "age_hours": hrs,
                        "timing_str": t_str,
                    })
                return res
    except Exception:
        pass
    return None

def probe_workable(slug, display_name):
    url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
    try:
        r = requests.post(url, json={}, headers=HEADERS, timeout=7)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("results", [])
            if jobs:
                res = []
                for j in jobs:
                    loc_parts = []
                    city = j.get("city")
                    country = j.get("country")
                    if city: loc_parts.append(city)
                    if country: loc_parts.append(country)
                    loc = ", ".join(loc_parts) or "Unspecified"
                    if j.get("telecommuting"):
                        loc = f"{loc} (Remote)".strip()
                    hrs, t_str = parse_timing(j.get("published_on") or j.get("created_at"))
                    shortcode = j.get("shortcode")
                    res.append({
                        "platform": "Workable",
                        "company": display_name,
                        "board_slug": slug,
                        "title": (j.get("title") or "").strip(),
                        "location": loc,
                        "url": f"https://apply.workable.com/{slug}/j/{shortcode}/" if shortcode else "",
                        "age_hours": hrs,
                        "timing_str": t_str,
                    })
                return res
    except Exception:
        pass
    return None

def probe_smartrecruiters(slug, display_name):
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    try:
        r = requests.get(url, headers=HEADERS, timeout=7)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("content", [])
            if jobs:
                res = []
                for j in jobs:
                    loc_obj = j.get("location") or {}
                    loc_parts = [p for p in [loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country")] if p]
                    loc = ", ".join(loc_parts) or "Unspecified"
                    if loc_obj.get("remote"):
                        loc = f"{loc} (Remote)".strip()
                    hrs, t_str = parse_timing(j.get("releasedDate"))
                    res.append({
                        "platform": "SmartRecruiters",
                        "company": display_name,
                        "board_slug": slug,
                        "title": (j.get("name") or "").strip(),
                        "location": loc,
                        "url": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}" if j.get("id") else "",
                        "age_hours": hrs,
                        "timing_str": t_str,
                    })
                return res
    except Exception:
        pass
    return None

def check_company(company_name):
    slugs = generate_slug_candidates(company_name)
    for s in slugs:
        # 1. Greenhouse
        res = probe_greenhouse(s, company_name)
        if res:
            return ("Greenhouse", s, res)
        # 2. Lever
        res = probe_lever(s, company_name)
        if res:
            return ("Lever", s, res)
        # 3. Ashby
        res = probe_ashby(s, company_name)
        if res:
            return ("Ashby", s, res)
        # 4. Workable
        res = probe_workable(s, company_name)
        if res:
            return ("Workable", s, res)
        # 5. SmartRecruiters
        res = probe_smartrecruiters(s, company_name)
        if res:
            return ("SmartRecruiters", s, res)
    return None

MAX_AGE_HOURS = 6.0  # STRICT RULE: Throw out all postings older than 6 hours

def filter_job(job, require_india_loc=True, max_hours=MAX_AGE_HOURS):
    title = job["title"].lower()
    location = job["location"].lower()

    # Title exclusions
    if any(ex in title for ex in EXCLUDE):
        return False

    # Title keyword match (word boundaries for intern/trainee to avoid 'internal')
    matched_kw = False
    for kw in KEYWORDS:
        if kw in ["intern", "trainee"]:
            if re.search(r"\b" + re.escape(kw) + r"\b", title):
                matched_kw = True
                break
        elif kw in title:
            matched_kw = True
            break
    if not matched_kw:
        return False

    # Location check
    if require_india_loc:
        if not any(loc in location for loc in INDIA_LOCATIONS):
            return False

    # STRICT 6-HOUR RULE: Throw out any job older than 6 hours or with unknown timestamp
    if max_hours is not None:
        if job["age_hours"] is None or job["age_hours"] > max_hours:
            return False

    return True

def main():
    parser = argparse.ArgumentParser(description="Scan company list across ATS job boards")
    parser.add_argument("--input", default="company_list.txt", help="Path to company list text file")
    parser.add_argument("--max-workers", type=int, default=16, help="Parallel worker threads")
    parser.add_argument("--all-locations", action="store_true", help="Include all global locations (skip India filter)")
    parser.add_argument("--all-time", action="store_true", help="Include jobs older than 6 hours")
    parser.add_argument("--output-json", default="discovered_jobs.json", help="Path to write JSON findings")
    parser.add_argument("--output-md", default="discovered_jobs.md", help="Path to write Markdown findings")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found.")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        raw_lines = [l.strip() for l in f if l.strip()]

    # Deduplicate while preserving first occurrence
    unique_companies = []
    seen = set()
    for l in raw_lines:
        c_clean = clean_company_name(l).lower()
        if c_clean not in seen:
            seen.add(c_clean)
            unique_companies.append(l)

    print(f"[*] Loaded {len(raw_lines)} lines -> {len(unique_companies)} unique companies.")
    print(f"[*] Scanning Greenhouse, Lever, Ashby, Workable, SmartRecruiters using {args.max_workers} threads...\n")

    discovered_boards = {}
    all_raw_jobs = []

    start_time = datetime.datetime.now()

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_company = {executor.submit(check_company, c): c for c in unique_companies}
        done_count = 0
        for future in as_completed(future_to_company):
            done_count += 1
            c = future_to_company[future]
            try:
                res = future.result()
                if res:
                    platform, slug, jobs = res
                    discovered_boards[c] = {
                        "platform": platform,
                        "slug": slug,
                        "total_jobs": len(jobs)
                    }
                    all_raw_jobs.extend(jobs)
                    print(f"  [+] [{done_count}/{len(unique_companies)}] FOUND {c} on {platform} ({slug}): {len(jobs)} active jobs")
                else:
                    if done_count % 30 == 0:
                        print(f"  [-] [{done_count}/{len(unique_companies)}] Progressing...")
            except Exception as e:
                pass

    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    print(f"\n[+] Scan complete in {elapsed:.1f}s!")
    print(f"[+] Discovered {len(discovered_boards)} companies with live public ATS boards!")
    print(f"[+] Total raw jobs across all boards: {len(all_raw_jobs)}")

    # Filter matching jobs
    filtered_jobs = []
    for j in all_raw_jobs:
        if filter_job(j, require_india_loc=not args.all_locations, max_hours=None if args.all_time else MAX_AGE_HOURS):
            filtered_jobs.append(j)

    # Sort: newest first
    filtered_jobs.sort(key=lambda x: x["age_hours"] if x["age_hours"] is not None else 999999)

    print(f"\n=======================================================")
    print(f"MATCHING PROFILE JOBS ({'All Active' if args.all_time else '< 6 Hours Old'} - India/Remote): {len(filtered_jobs)}")
    print(f"=======================================================\n")

    for idx, j in enumerate(filtered_jobs[:20], 1):
        print(f"[{idx}] {j['title']} @ {j['company']} ({j['platform']})")
        print(f"    Location: {j['location']}")
        print(f"    Posted:   {j['timing_str']}")
        print(f"    URL:      {j['url']}\n")

    # Save to JSON
    summary_data = {
        "scan_time": datetime.datetime.now(IST_TZ).isoformat(),
        "total_companies_scanned": len(unique_companies),
        "discovered_boards_count": len(discovered_boards),
        "discovered_boards": discovered_boards,
        "matched_jobs_count": len(filtered_jobs),
        "matched_jobs": filtered_jobs,
    }
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)
    print(f"[+] Saved structured data to {args.output_json}")

    # Generate Markdown report
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(f"# ATS Job Scan Results\n\n")
        f.write(f"- **Scan Time:** {datetime.datetime.now(IST_TZ).strftime('%d %b %Y, %I:%M %p IST')}\n")
        f.write(f"- **Companies Scanned:** {len(unique_companies)}\n")
        f.write(f"- **Active ATS Boards Discovered:** {len(discovered_boards)}\n")
        f.write(f"- **Matched Software/Engineering Roles (India/Remote):** {len(filtered_jobs)}\n\n")

        f.write("## Discovered ATS Boards\n\n")
        f.write("| Company | ATS Platform | Board Slug | Total Active Openings |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for comp, info in sorted(discovered_boards.items(), key=lambda x: x[0].lower()):
            f.write(f"| {comp} | **{info['platform']}** | `{info['slug']}` | {info['total_jobs']} |\n")

        f.write("\n## Curated Matches for Abhijeet\n\n")
        f.write("| # | Role | Company | Location | Platform | Posted | Link |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for i, j in enumerate(filtered_jobs, 1):
            title = j['title'].replace('|', '/')
            comp = j['company'].replace('|', '/')
            loc = j['location'].replace('|', '/')
            timing = j['timing_str'].replace('|', '/')
            url = j['url']
            f.write(f"| {i} | **{title}** | {comp} | {loc} | {j['platform']} | {timing} | [Apply]({url}) |\n")

    print(f"[+] Saved readable markdown report to {args.output_md}")

if __name__ == "__main__":
    main()
