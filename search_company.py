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

# ==============================================================================
# RESUME-CURATED ROLE QUALIFICATION & EXCLUSION RULES
# ==============================================================================
DISQUALIFIED_WORDS = {
    # 1. Quality Assurance / Testing / SDET / Verification
    "quality", "qa", "qc", "sdet", "test", "testing", "tester", "qualification",
    "validation", "verification",

    # 2. Firmware / Embedded / Hardware / Electronics
    "firmware", "embedded", "microcontroller", "microprocessor", "dsp", "rtos",
    "bsp", "fpga", "asic", "soc", "vlsi", "pcb", "hardware", "silicon",
    "semiconductor", "chipset", "verilog", "vhdl", "bringup",

    # 3. Non-software engineering disciplines
    "manufacturing", "mechanical", "electrical", "electronic", "electronics",
    "civil", "chemical", "aerospace", "aviation", "avionics", "automotive",
    "structural", "industrial", "mechatronics", "optical", "optics", "acoustic",
    "petroleum", "nuclear", "metallurgical", "biomedical", "materials",
    "process", "welding", "piping", "thermal", "cad", "cam", "aerodynamic",
    "chassis", "powertrain", "flight", "propulsion", "hvac", "environmental",
    "facilities", "plant", "maintenance", "safety", "reliability",

    # 4. Non-tech business domains
    "sales", "account", "marketing", "recruiter", "recruiting", "sourcer",
    "talent", "hr", "finance", "accounting", "auditor", "audit", "legal",
    "counsel", "compliance", "tax", "scrum", "agile", "designer", "graphic",
    "art", "copywriter", "helpdesk", "logistics", "warehouse", "procurement",
    "consultant", "risk", "growth",

    # 5. Seniority and management
    "senior", "sr", "lead", "principal", "director", "manager", "head",
    "vp", "chief", "fellow", "distinguished", "expert", "smts", "lmts",
    "pmts", "experienced", "architect",
}

DISQUALIFIED_PHRASES = [
    "human resources", "product manager", "project manager", "program manager",
    "customer support", "technical support", "service desk", "supply chain",
    "quality assurance", "quality engineer", "firmware engineer", "embedded engineer",
    "hardware engineer", "field engineer", "network engineer", "system administrator",
    "tech lead", "team lead",
]

LEVEL_REGEX = re.compile(
    r"\b(?:sde|swe|mts|engineer|developer)\s*[-_ ]*(?:ii|iii|iv|v|2|3|4|5)\b"
    r"|\b(?:level|lvl|grade|band|l)\s*[-_ ]*(?:ii|iii|iv|v|2|3|4|5|6)\b"
    r"|\b(?:mid|mid-level|experienced)\b",
    re.IGNORECASE,
)

STAFF_REGEX = re.compile(r"(?<!member of technical )\bstaff\b", re.IGNORECASE)

TECH_ROLES_REGEX = re.compile(
    r"\b(?:software\s+(?:engineer|developer|development\s+engineer|development|dev)"
    r"|sde|swe|programmer"
    r"|full[\s-]*stack(?:\s+(?:engineer|developer|dev|software))?"
    r"|back[\s-]*end(?:\s+(?:engineer|developer|dev|software))?"
    r"|front[\s-]*end(?:\s+(?:engineer|developer|dev|software))?"
    r"|(?:java|spring\s*boot|spring)\s+(?:developer|engineer|software|backend|full[\s-]*stack|dev)"
    r"|web\s+(?:developer|engineer)"
    r"|application\s+(?:developer|software|engineer)"
    r"|member\s+of\s+technical\s+staff|mts"
    r"|associate\s+software|junior\s+software|graduate\s+software"
    r"|graduate\s+engineer\s+trainee|get)\b",
    re.IGNORECASE,
)

INTERN_INDICATORS_REGEX = re.compile(
    r"\b(?:intern|internship|co-op|coop|trainee|apprentice|fellowship)\b",
    re.IGNORECASE,
)

INTERN_TECH_CONTEXT_REGEX = re.compile(
    r"\b(?:software|engineer|engineering|developer|development|sde|swe|backend|frontend|full[\s-]*stack"
    r"|java|spring|web|tech|technology|summer|campus|student|undergraduate|computer\s+science"
    r"|r&d|research|data\s+engineering|ai|ml|machine\s+learning|cloud|graduate)\b",
    re.IGNORECASE,
)

INDIA_LOCATIONS = [
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "delhi", "noida",
    "gurgaon", "gurugram", "chennai", "mumbai", "ahmedabad", "kolkata",
    "kochi", "coimbatore", "chandigarh", "indore", "jaipur",
]

GLOBAL_REMOTE_TOKENS = [
    "anywhere", "worldwide", "global", "work from anywhere",
]

FOREIGN_DOMESTIC_COUNTRIES = [
    "england", "united kingdom", "uk", "great britain", "gb", "germany", "deutschland",
    "de", "france", "fr", "canada", "ca", "australia", "au", "netherlands", "nl",
    "poland", "pl", "spain", "es", "singapore", "sg", "ireland", "ie",
    "sweden", "se", "italy", "it", "switzerland", "ch", "brazil", "br",
    "japan", "jp", "united states", "usa", "us", "mexico", "mx", "philippines",
    "israel", "il", "china", "cn", "taiwan", "tw", "new zealand", "nz",
]
FOREIGN_COUNTRY_REGEX = re.compile(
    r"\b(?:" + "|".join(re.escape(c) for c in FOREIGN_DOMESTIC_COUNTRIES) + r")\b",
    re.IGNORECASE,
)

MAX_AGE_HOURS = 24.0

def is_qualified_role(title):
    t = title.lower()
    words = set(re.findall(r"[a-zA-Z0-9]+", t))
    for p in DISQUALIFIED_PHRASES:
        if p in t:
            return False, f"disqualified phrase: {p}"
    disq = words.intersection(DISQUALIFIED_WORDS)
    if disq:
        return False, f"disqualified word: {', '.join(disq)}"
    if STAFF_REGEX.search(t):
        return False, "staff role"
    if LEVEL_REGEX.search(t):
        return False, "mid/senior level"
    if INTERN_INDICATORS_REGEX.search(t):
        if INTERN_TECH_CONTEXT_REGEX.search(t):
            return True, "qualified intern"
        return False, "intern without tech context"
    if TECH_ROLES_REGEX.search(t):
        return True, "qualified software role"
    return False, "does not match software/tech target profile"

def is_target_location(location_str):
    if not location_str:
        return True, "unspecified"
    loc = location_str.lower().strip()
    if any(city in loc for city in INDIA_LOCATIONS):
        return True, "india"
    if any(token in loc for token in GLOBAL_REMOTE_TOKENS):
        return True, "worldwide_remote"
    if "remote" in loc or "work from home" in loc:
        if FOREIGN_COUNTRY_REGEX.search(loc):
            return False, "domestic_foreign_remote"
        return True, "generic_remote"
    return False, "non_target_location"

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


WORKDAY_COMPANIES = {
    "salesforce": ("salesforce.wd12.myworkdayjobs.com", "salesforce", "External_Career_Site", "Salesforce"),
    "nvidia": ("nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite", "NVIDIA"),
    "adobe": ("adobe.wd5.myworkdayjobs.com", "adobe", "external_experienced", "Adobe"),
    "workday": ("workday.wd5.myworkdayjobs.com", "workday", "Workday", "Workday"),
    "target": ("target.wd5.myworkdayjobs.com", "target", "targetcareers", "Target"),
    "mastercard": ("mastercard.wd1.myworkdayjobs.com", "mastercard", "CorporateCareers", "Mastercard"),
    "paypal": ("paypal.wd1.myworkdayjobs.com", "paypal", "jobs", "PayPal"),
    "autodesk": ("autodesk.wd1.myworkdayjobs.com", "autodesk", "Ext", "Autodesk"),
}

def fetch_company_jobs(slug):
    slug_clean = slug.strip().lower().replace(" ", "")
    results = []

    # 0. Check Amazon
    if slug_clean == "amazon":
        url = "https://www.amazon.jobs/en/search.json?base_query=software+engineer&country=IND&result_limit=25"
        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            if r.status_code == 200:
                for j in r.json().get("jobs", []):
                    hrs, t_str = parse_timing(j.get("posted_date"))
                    job_path = j.get("job_path", "")
                    results.append({
                        "source": "Amazon Jobs",
                        "company": "Amazon",
                        "title": (j.get("title") or "").strip(),
                        "location": (j.get("location") or "India").strip(),
                        "url": f"https://www.amazon.jobs{job_path}" if job_path else "https://www.amazon.jobs",
                        "age_hours": hrs,
                        "timing_str": t_str,
                    })
                if results:
                    return "Amazon Jobs", results
        except Exception:
            pass

    # 0. Check Workday
    if slug_clean in WORKDAY_COMPANIES:
        host, tenant, site_id, display_name = WORKDAY_COMPANIES[slug_clean]
        url = f"https://{host}/wday/cxs/{tenant}/{site_id}/jobs"
        try:
            r = requests.post(url, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}, headers=HEADERS, timeout=8)
            if r.status_code == 200:
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                for j in r.json().get("jobPostings", []):
                    ext_path = j.get("externalPath", "")
                    posted_str = j.get("postedOn", "")
                    hrs = None
                    if "today" in posted_str.lower():
                        hrs = 2.0
                    elif "yesterday" in posted_str.lower():
                        hrs = 18.0
                    elif "day" in posted_str.lower() or "30+" in posted_str:
                        hrs = 72.0
                    results.append({
                        "source": "Workday",
                        "company": display_name,
                        "title": (j.get("title") or "").strip(),
                        "location": (j.get("locationsText") or "Unspecified").strip(),
                        "url": f"https://{host}/en-US/{site_id}{ext_path}" if ext_path else "",
                        "age_hours": hrs,
                        "timing_str": posted_str or "Active Opening",
                    })
                if results:
                    return "Workday", results
        except Exception:
            pass

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
        # 1. Role capability check
        role_ok, _ = is_qualified_role(j["title"])
        if not role_ok:
            continue

        # 2. Location check
        loc_ok, _ = is_target_location(j["location"])
        if not loc_ok:
            continue

        # 3. Max age check (unless --all is specified)
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
