#!/usr/bin/env python3
"""
job_watcher.py - Poll public ATS job-board APIs and alert on NEW postings via Telegram.

Curated specifically for Abhijeet Singh:
  - Profile: B.Tech Computer Science & Engineering (Core), 2023 - 2027 Batch (VIT-AP University)
  - Target Roles:
      1. Software Engineer / SDE / SWE (Fresher, Junior, Associate, Entry-Level, Grad)
      2. Java Developer / Spring Boot Backend Engineer / Full-Stack Developer (Java/Web)
      3. Member of Technical Staff (MTS-1) / Graduate Engineer Trainee (GET)
      4. Tech Internships: Software Engineering Intern, SDE Intern, SWE Intern,
         Backend/Frontend/Full-Stack Intern, Developer Intern, Summer/Campus Tech Intern
  - Strict Disqualifications:
      1. Quality / QA / SDET / Testing / Qualification / Validation / Verification roles
      2. Firmware / Embedded / Microcontroller / Hardware / Silicon / VLSI / DSP roles
      3. Non-software disciplines (Manufacturing, Mechanical, Electrical, Civil, Aerospace, etc.)
      4. Non-tech domains (Sales, Marketing, HR, Finance, Legal, Support, Management, etc.)
      5. Senior & Experienced levels (Senior, Lead, Principal, Staff, SDE 2+, SWE II+, etc.)
  - Deduplication: Multi-layer (ATS Job ID + Base Requisition ID + Canonical URL + Semantic Content Fingerprint)
  - Concurrency: Strict OS-level single-instance lock to prevent duplicate daemon processes

Setup:
  1. Create a bot with @BotFather on Telegram -> TELEGRAM_BOT_TOKEN
  2. Send a message to your bot, then open:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     to find your "chat": {"id": ...} -> TELEGRAM_CHAT_ID
  3. Set environment variables:
     $env:TELEGRAM_BOT_TOKEN="your_token"
     $env:TELEGRAM_CHAT_ID="your_chat_id"

Usage:
  py job_watcher.py                      # Runs daemon loop every POLL_SECONDS (15m)
  py job_watcher.py --once               # Runs a single pass and exits
  py job_watcher.py --dry-run            # Inspect all current active matching jobs without DB writes
  py job_watcher.py --find-internships   # Discover all currently active tech internships
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import os
import re
import sqlite3
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watcher.log")


class TeeLogger:
    def __init__(self, filepath, stream):
        self.stream = stream
        try:
            self.f = open(filepath, "a", encoding="utf-8")
        except Exception:
            self.f = None

    def write(self, data):
        if self.stream:
            try:
                self.stream.write(data)
            except Exception:
                pass
        if self.f:
            try:
                self.f.write(data)
                self.f.flush()
            except Exception:
                pass

    def flush(self):
        if self.stream:
            try:
                self.stream.flush()
            except Exception:
                pass
        if self.f:
            try:
                self.f.flush()
            except Exception:
                pass


sys.stdout = TeeLogger(LOG_PATH, sys.stdout)
sys.stderr = TeeLogger(LOG_PATH, sys.stderr)

import requests

# ==============================================================================
# SINGLE INSTANCE PROCESS LOCK (Prevents duplicate instances & duplicate alerts)
# ==============================================================================
LOCK_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".watcher.lock")


class SingleInstanceLock:
    def __init__(self, filepath=LOCK_FILE_PATH):
        self.filepath = filepath
        self.file_handle = None

    def acquire(self):
        try:
            self.file_handle = open(self.filepath, "w")
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.file_handle.write(f"{os.getpid()}\n")
            self.file_handle.flush()
            return True
        except (IOError, OSError, PermissionError):
            if self.file_handle:
                try:
                    self.file_handle.close()
                except Exception:
                    pass
                self.file_handle = None
            return False

    def release(self):
        if self.file_handle:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self.file_handle.seek(0)
                    msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file_handle.fileno(), fcntl.LOCK_UN)
                self.file_handle.close()
            except Exception:
                pass
            self.file_handle = None
        try:
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
        except Exception:
            pass


# ==============================================================================
# COMPANY BOARDS (241 High-Signal Tech Companies)
# ==============================================================================
COMPANIES = {
    "greenhouse": [
        "affirm", "agoda", "airbnb", "airtable", "algolia", "appian", "applovin",
        "appnovation", "asana", "aweber", "block", "branch", "brex", "calendly",
        "canonical", "chargepoint", "circleci", "clear", "cloudflare", "cockroachlabs",
        "coinbase", "constantcontact", "contentful", "coursera", "css", "databricks",
        "datadog", "deliveroo", "discord", "drc", "dropbox", "druva", "duolingo",
        "elastic", "epicgames", "faire", "fastly", "fastspring", "figma", "fivetran",
        "flexport", "gateway", "ghost", "gitlab", "gocardless", "godaddy", "grafanalabs",
        "graphcore", "groww", "gusto", "hackerrank", "highradius", "inmobi", "instacart",
        "intercom", "kaseya", "khanacademy", "klaviyo", "lyft", "medium", "mixpanel",
        "mongodb", "monzo", "netcracker", "netlify", "newrelic", "nintex", "nix",
        "nuro", "observeai", "okta", "pagerduty", "pantheon", "pine", "pingidentity",
        "pinterest", "planetscale", "porter", "ramp", "razorpaysoftwareprivatelimited",
        "reddit", "remote", "riotgames", "robinhood", "roblox", "rubrik", "samsara",
        "saucelabs", "scaleai", "singlestore", "slice", "smartsheet", "sofi", "space",
        "squarespace", "stripe", "sumup", "tebra", "thoughtworks", "tripadvisor",
        "trivago", "truecaller", "turing", "twilio", "typeform", "udemy", "unbounce",
        "upwork", "valtech", "veeamsoftware", "vercel", "waymo", "wise", "wrike",
        "zinnov", "zoominfo", "zscaler",
    ],
    "ashby": [
        "amplitude", "bounce", "clarion", "clerk", "clickhouse", "clickup", "crisp",
        "cursor", "deliveroo", "euphoric", "g2", "ghost", "glitch", "helpscout",
        "hopper", "infinite", "kayak", "linear", "miro", "modal", "navi", "neon",
        "notion", "nubank", "openai", "paddle", "perplexity", "plaid", "posthog",
        "prompt", "quora", "ramp", "redis", "render", "sentry", "sisense",
        "snowflake", "snyk", "substack", "supabase", "temporal", "thought-machine",
        "tractable", "trulioo", "webflow", "xero", "zapier", "zilch",
    ],
    "lever": [
        "activecampaign", "cred", "eleks", "fampay", "hevodata", "linkedin",
        "meesho", "mendix", "mindtickle", "neon", "omnisend", "outreach",
        "palantir", "paytm", "porter", "spotify", "toptal", "vogo",
        "wavicledata", "zeta", "zoox", "zopa",
    ],
    "smartrecruiters": [
        "alten", "atossyntel", "azilen", "bytedance", "canva", "cars24",
        "endava", "fiverr", "freecharge", "freshworks", "getmyuni", "gong",
        "grab", "hackerrank", "innov8", "interviewbit", "ixigo", "kelltontech",
        "kredx", "lastminutecom", "lendingkart", "loginext", "lucidchart",
        "mindtickle", "newrelic", "newtonschool", "nobroker", "nousinfosystems",
        "nowfloats", "palantir", "servicenow", "shipsy", "sigmasoftware",
        "skill-lync", "sutherland", "swiggy", "turtlemint", "uber", "unacademy",
        "upstox", "valuelabs", "wayfair", "whatfix", "wiingy", "wise",
    ],
    "workday": [
        "adobe", "autodesk", "mastercard", "nvidia", "paypal", "salesforce",
        "target", "workday",
    ],
    "amazon": [
        "amazon",
    ],
}

# ==============================================================================
# RESUME-CURATED ROLE QUALIFICATION & EXCLUSION RULES
# ==============================================================================
# Strict disqualification: Quality / QA / SDET / Testing / Qualification
# Strict disqualification: Firmware / Embedded / Hardware / Silicon
# Strict disqualification: Non-software disciplines
# Strict disqualification: Non-tech domains & Seniority
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

# Full-time qualified software roles
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

# Internship indicator
INTERN_INDICATORS_REGEX = re.compile(
    r"\b(?:intern|internship|co-op|coop|trainee|apprentice|fellowship)\b",
    re.IGNORECASE,
)

# Tech context requirement for internships
INTERN_TECH_CONTEXT_REGEX = re.compile(
    r"\b(?:software|engineer|engineering|developer|development|sde|swe|backend|frontend|full[\s-]*stack"
    r"|java|spring|web|tech|technology|summer|campus|student|undergraduate|computer\s+science"
    r"|r&d|research|data\s+engineering|ai|ml|machine\s+learning|cloud|graduate)\b",
    re.IGNORECASE,
)

# Target locations (India tech hubs & global remote)
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

MAX_AGE_HOURS = 24.0         # Full-time roles: <= 24 hours old
MAX_INTERN_AGE_HOURS = 72.0  # Tech Internships: <= 72 hours old (covers 3-day / weekend postings)
POLL_SECONDS = 900           # Scan every 15 minutes
DB_PATH = "seen_jobs.db"

# ==============================================================================
# ENVIRONMENT & INITIALIZATION
# ==============================================================================
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


# ==============================================================================
# DEDUPLICATION & CANONICALIZATION ENGINE
# ==============================================================================
def clean_url(raw_url):
    """Normalize ATS URLs by stripping tracking tokens, query parameters, and fragments."""
    if not raw_url:
        return ""
    try:
        parsed = urlparse(raw_url.strip())
        ignored_params = {
            "gh_src", "lever-source", "source", "ref", "utm_source",
            "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "mode", "s", "sub_source", "iis", "iisn", "jobboardsource",
            "req", "c",
        }
        filtered_q = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in ignored_params]
        filtered_q.sort(key=lambda x: x[0])
        new_query = urlencode(filtered_q)
        path = parsed.path.rstrip("/")
        # Remove trailing /apply to canonicalize to job posting page
        if path.endswith("/apply"):
            path = path[:-6]
        return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", new_query, ""))
    except Exception:
        return raw_url.strip()


def normalize_title(title):
    """Normalize job title for semantic deduplication across equivalent job listings."""
    t = (title or "").lower()
    # Strip parentheses and brackets
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    # Normalize common abbreviations and equivalents
    t = re.sub(r"\b(?:software development engineer|software dev engineer|software developer|software dev|sde|swe)\b", "software engineer", t)
    t = re.sub(r"\b(?:internship|co-op|coop|apprentice)\b", "intern", t)
    t = re.sub(r"\b(?:full[\s-]*stack)\b", "fullstack", t)
    t = re.sub(r"\b(?:back[\s-]*end)\b", "backend", t)
    t = re.sub(r"\b(?:front[\s-]*end)\b", "frontend", t)
    t = re.sub(r"\b(?:spring\s*boot)\b", "spring", t)
    t = re.sub(r"[^a-zA-Z0-9]+", " ", t).strip()
    return t


def compute_job_fingerprint(company, title, location):
    """Compute normalized content fingerprint to deduplicate re-postings."""
    comp = re.sub(r"[^a-zA-Z0-9]+", "", (company or "").lower())
    comp = re.sub(r"(softwareprivatelimited|pvtltd|ltd|inc|corporation|corp|technologies|solutions)", "", comp)

    norm_t = normalize_title(title)

    loc_raw = (location or "").lower()
    loc_norm = "other"
    if "remote" in loc_raw or "anywhere" in loc_raw or "work from home" in loc_raw:
        loc_norm = "remote"
    elif any(city in loc_raw for city in INDIA_LOCATIONS):
        loc_norm = "india"

    raw_str = f"{comp}:{norm_t}:{loc_norm}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


def get_base_job_id(job_id):
    """Strip duplicate listing suffixes like -1, -2, _1 from job requisition IDs."""
    if not job_id:
        return ""
    return re.sub(r"[-_]\d+$", "", job_id)


def init_database(db_path=DB_PATH):
    """Initialize SQLite database with DELETE journal mode (100% self-contained in single file)."""
    conn = sqlite3.connect(db_path, timeout=15)
    # Flush any leftover WAL data into the main database file
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    except Exception:
        pass
    conn.execute("PRAGMA journal_mode = DELETE;")
    conn.execute("PRAGMA synchronous = FULL;")
    conn.execute("PRAGMA busy_timeout = 10000;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen (
            id TEXT PRIMARY KEY,
            company TEXT,
            first_seen REAL,
            fingerprint TEXT,
            title TEXT,
            location TEXT,
            url TEXT,
            notified INTEGER DEFAULT 0
        )
        """
    )
    # Perform column migrations if needed
    cur = conn.cursor()
    existing_cols = [c[1] for c in cur.execute("PRAGMA table_info(seen)").fetchall()]
    for col, ctype in [
        ("fingerprint", "TEXT"),
        ("title", "TEXT"),
        ("location", "TEXT"),
        ("url", "TEXT"),
        ("notified", "INTEGER DEFAULT 0"),
    ]:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE seen ADD COLUMN {col} {ctype}")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_seen_fingerprint ON seen(fingerprint)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_seen_url ON seen(url)")
    conn.commit()
    return conn


def is_duplicate(db, job_id, clean_url_str, fingerprint, window_days=30):
    """Check ATS ID, Base Requisition ID, canonical URL, and content fingerprint."""
    cutoff = time.time() - (window_days * 86400)

    # 1. Exact ATS ID match
    if db.execute("SELECT 1 FROM seen WHERE id = ?", (job_id,)).fetchone():
        return True, "id"

    # 2. Base ATS ID match (e.g. wd:paypal:R0138270-1 vs wd:paypal:R0138270)
    base_id = get_base_job_id(job_id)
    if base_id and base_id != job_id:
        if db.execute("SELECT 1 FROM seen WHERE id = ?", (base_id,)).fetchone():
            return True, "base_id"

    # 3. Canonical URL match
    if clean_url_str:
        if db.execute(
            "SELECT 1 FROM seen WHERE url = ? AND (first_seen > ? OR first_seen IS NULL)",
            (clean_url_str, cutoff),
        ).fetchone():
            return True, "url"

    # 4. Content Fingerprint match (within rolling 30-day window)
    if fingerprint:
        if db.execute(
            "SELECT 1 FROM seen WHERE fingerprint = ? AND (first_seen > ? OR first_seen IS NULL)",
            (fingerprint, cutoff),
        ).fetchone():
            return True, "fingerprint"

    return False, None


def mark_job_seen(db, job_id, company, fingerprint, title, location, clean_url_str, notified=0):
    """Record a job in the database and commit immediately to avoid race conditions."""
    db.execute(
        """
        INSERT OR REPLACE INTO seen (id, company, first_seen, fingerprint, title, location, url, notified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (job_id, company, time.time(), fingerprint, title, location, clean_url_str, notified),
    )
    db.commit()


# ==============================================================================
# ATS FETCHERS
# ==============================================================================
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
        timeout=10,
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


def fetch_smartrecruiters(slug):
    r = requests.get(
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    for j in r.json().get("content", []):
        loc_obj = j.get("location") or {}
        loc_parts = [p for p in [loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country")] if p]
        loc = ", ".join(loc_parts) or "Unspecified"
        if loc_obj.get("remote"):
            loc = f"{loc} (Remote)".strip()
        dt = parse_datetime(j.get("releasedDate"))
        yield {
            "id": f"sr:{slug}:{j.get('id')}",
            "title": (j.get("name") or "").strip(),
            "location": loc,
            "url": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}" if j.get("id") else "",
            "company": slug.title(),
            "source": "SmartRecruiters",
            "posted_at": dt,
            "timing_str": format_timing(dt),
        }


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


def fetch_workday(slug):
    info = WORKDAY_COMPANIES.get(slug)
    if not info:
        return
    host, tenant, site_id, display_name = info
    url = f"https://{host}/wday/cxs/{tenant}/{site_id}/jobs"
    payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
    r = requests.post(url, json=payload, headers=HEADERS, timeout=10)
    r.raise_for_status()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    for j in r.json().get("jobPostings", []):
        ext_path = j.get("externalPath", "")
        job_url = f"https://{host}/en-US/{site_id}{ext_path}" if ext_path else ""
        posted_str = j.get("postedOn", "")
        dt = None
        if "today" in posted_str.lower():
            dt = now_utc - datetime.timedelta(hours=2)
        elif "yesterday" in posted_str.lower():
            dt = now_utc - datetime.timedelta(hours=18)
        elif "day" in posted_str.lower() or "30+" in posted_str:
            dt = now_utc - datetime.timedelta(days=3)

        clean_id = ext_path.split("_")[-1] if "_" in ext_path else ext_path
        job_id = f"wd:{slug}:{clean_id}"
        yield {
            "id": job_id,
            "title": (j.get("title") or "").strip(),
            "location": (j.get("locationsText") or "Unspecified").strip(),
            "url": job_url,
            "company": display_name,
            "source": "Workday",
            "posted_at": dt,
            "timing_str": posted_str or "Active Opening",
        }


def fetch_amazon(slug="amazon"):
    """Fetch software engineer and tech intern postings from Amazon Jobs."""
    queries = [
        "https://www.amazon.jobs/en/search.json?base_query=software+engineer&country=IND&result_limit=40",
        "https://www.amazon.jobs/en/search.json?base_query=intern&country=IND&result_limit=40",
        "https://www.amazon.jobs/en/search.json?base_query=student&country=IND&result_limit=40",
    ]
    seen_amazon_ids = set()
    for url in queries:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            for j in r.json().get("jobs", []):
                raw_id = j.get("id_icims") or j.get("id")
                if not raw_id or raw_id in seen_amazon_ids:
                    continue
                seen_amazon_ids.add(raw_id)
                job_id = f"az:amazon:{raw_id}"
                posted_date_str = j.get("posted_date", "")
                dt = None
                if posted_date_str:
                    try:
                        dt = datetime.datetime.strptime(posted_date_str, "%B %d, %Y").replace(tzinfo=datetime.timezone.utc)
                    except Exception:
                        pass
                job_path = j.get("job_path", "")
                job_url = f"https://www.amazon.jobs{job_path}" if job_path else "https://www.amazon.jobs"
                yield {
                    "id": job_id,
                    "title": (j.get("title") or "").strip(),
                    "location": (j.get("location") or j.get("normalized_location") or "India").strip(),
                    "url": job_url,
                    "company": "Amazon",
                    "source": "Amazon Jobs",
                    "posted_at": dt,
                    "timing_str": format_timing(dt) if dt else (posted_date_str or "Active Opening"),
                }
        except Exception:
            pass


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
    "workday": fetch_workday,
    "amazon": fetch_amazon,
}


def fetch_company_safe(item):
    source, slug = item
    fetcher = FETCHERS.get(source)
    if not fetcher:
        return source, slug, []
    try:
        jobs = list(fetcher(slug))
        return source, slug, jobs
    except Exception:
        return source, slug, None


# ==============================================================================
# MATCHING & RESUME QUALIFICATION ENGINE
# ==============================================================================
def is_qualified_role(title):
    """Determine whether the title qualifies for Abhijeet Singh's profile."""
    t = title.lower()
    words = set(re.findall(r"[a-zA-Z0-9]+", t))

    # 1. Disqualified phrases
    for p in DISQUALIFIED_PHRASES:
        if p in t:
            return False, f"disqualified phrase: {p}"

    # 2. Disqualified individual tokens (Quality, Firmware, Mechanical, Sales, HR, etc.)
    disq = words.intersection(DISQUALIFIED_WORDS)
    if disq:
        return False, f"disqualified word: {', '.join(disq)}"

    # 3. Staff exclusion (except Member of Technical Staff)
    if STAFF_REGEX.search(t):
        return False, "staff role"

    # 4. Level exclusions (e.g. SDE 2, SWE II)
    if LEVEL_REGEX.search(t):
        return False, "mid/senior level"

    # 5. Tech Internships & Student campus roles
    if INTERN_INDICATORS_REGEX.search(t):
        if INTERN_TECH_CONTEXT_REGEX.search(t):
            return True, "qualified intern"
        return False, "intern without tech context"

    # 6. Full-Time Software / Tech roles
    if TECH_ROLES_REGEX.search(t):
        return True, "qualified software role"

    return False, "does not match software/tech target profile"


def is_target_location(location_str):
    """Verify location matches India hubs, Global remote, or generic remote."""
    if not location_str:
        return True, "unspecified"
    loc = location_str.lower().strip()

    # Match India cities / regions
    if any(city in loc for city in INDIA_LOCATIONS):
        return True, "india"

    # Match explicitly global / worldwide remote
    if any(token in loc for token in GLOBAL_REMOTE_TOKENS):
        return True, "worldwide_remote"

    # Check remote without domestic foreign country restrictions
    if "remote" in loc or "work from home" in loc:
        if FOREIGN_COUNTRY_REGEX.search(loc):
            return False, "domestic_foreign_remote"
        return True, "generic_remote"

    return False, "non_target_location"


def matches(job, enforce_max_age=True, max_age_hours=MAX_AGE_HOURS):
    """Full qualification pipeline for candidate Abhijeet Singh."""
    title = job.get("title", "")
    loc = job.get("location", "")

    # 1. Role capability evaluation
    role_ok, _ = is_qualified_role(title)
    if not role_ok:
        return False

    # 2. Location evaluation
    loc_ok, _ = is_target_location(loc)
    if not loc_ok:
        return False

    # 3. Freshness evaluation
    if enforce_max_age:
        if not job.get("posted_at"):
            return False
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        age_hours = (now_utc - job["posted_at"]).total_seconds() / 3600.0

        # Allow generous 72h window for tech internships, 24h for full-time software roles
        is_intern = bool(INTERN_INDICATORS_REGEX.search(title))
        allowed_age = MAX_INTERN_AGE_HOURS if is_intern else max_age_hours

        if age_hours > allowed_age or age_hours < -2.0:
            return False

    return True


# ==============================================================================
# NOTIFICATION SYSTEM
# ==============================================================================
def notify(job, dry_run=False):
    is_intern = bool(INTERN_INDICATORS_REGEX.search(job.get("title", "")))
    category_title = "Tech Internship Match" if is_intern else "Software Job Match"

    text = (
        f"🎯 [New {category_title}]\n"
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

    icon = "🎓" if is_intern else "🎯"
    tg_html = (
        f"{icon} <b>New {category_title}</b>\n\n"
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


# ==============================================================================
# POLLING ENGINE WITH MULTI-LAYER DEDUPLICATION
# ==============================================================================
def poll_cycle(db, dry_run=False, max_age=MAX_AGE_HOURS, find_internships=False):
    total_found = 0
    all_matched = []

    tasks = []
    for source, slugs in COMPANIES.items():
        for slug in slugs:
            tasks.append((source, slug))

    print(f"[*] Polling {len(tasks)} company boards concurrently across ATS platforms...")
    start_t = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        for source, slug, jobs in executor.map(fetch_company_safe, tasks):
            if jobs is None:
                continue
            total_found += len(jobs)

            for job in jobs:
                norm_url = clean_url(job.get("url", ""))
                fingerprint = compute_job_fingerprint(job["company"], job["title"], job.get("location", ""))

                if find_internships:
                    # Internship discovery mode (active openings, without age restriction)
                    if INTERN_INDICATORS_REGEX.search(job.get("title", "")):
                        if matches(job, enforce_max_age=False):
                            all_matched.append(job)
                    continue

                if dry_run:
                    if matches(job, enforce_max_age=True, max_age_hours=max_age):
                        all_matched.append(job)
                    continue

                # Strict Deduplication Check: ATS ID + Base ID + Canonical URL + Fingerprint
                dup, dup_reason = is_duplicate(db, job["id"], norm_url, fingerprint)
                if dup:
                    continue

                # Evaluate qualification against Abhijeet Singh's profile
                is_match = matches(job, enforce_max_age=True, max_age_hours=max_age)

                if is_match:
                    # Mark seen & commit BEFORE notification to prevent duplicate alerts
                    mark_job_seen(
                        db, job["id"], slug, fingerprint,
                        job["title"], job.get("location", ""), norm_url, notified=1
                    )
                    all_matched.append(job)
                    notify(job, dry_run=False)
                    time.sleep(0.3)  # Gentle spacing for Telegram rate limits
                else:
                    # Record seen with notified=0 so we don't re-scan it as new
                    mark_job_seen(
                        db, job["id"], slug, fingerprint,
                        job["title"], job.get("location", ""), norm_url, notified=0
                    )

    duration = time.time() - start_t
    print(f"[+] Completed scan of {len(tasks)} boards in {duration:.1f}s.")

    if find_internships:
        print(f"    Total active jobs: {total_found} | Qualified active tech internships: {len(all_matched)}")
        all_matched.sort(
            key=lambda x: x["posted_at"].timestamp() if x.get("posted_at") else 0,
            reverse=True,
        )
        print("\n================ ACTIVE TECH INTERNSHIPS ================")
        for job in all_matched:
            notify(job, dry_run=True)
        return total_found, len(all_matched)

    print(f"    Total active jobs: {total_found} | Qualified fresh matches: {len(all_matched)}")

    if dry_run:
        all_matched.sort(
            key=lambda x: x["posted_at"].timestamp() if x.get("posted_at") else 0,
            reverse=True,
        )
        print("\n==================================================")
        for job in all_matched:
            notify(job, dry_run=True)

    return total_found, len(all_matched)


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="ATS Job Watcher daemon (Curated for Abhijeet Singh)")
    parser.add_argument("--once", action="store_true", help="Run one poll pass and exit")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect all current active matching jobs without writing to DB",
    )
    parser.add_argument(
        "--max-age",
        type=float,
        default=MAX_AGE_HOURS,
        help="Max job age in hours for full-time roles (default: 24.0)",
    )
    parser.add_argument(
        "--find-internships",
        action="store_true",
        help="Discover all currently active tech internships across all company boards",
    )
    args = parser.parse_args()

    # Enforce strict single-instance process lock
    lock = None
    if not (args.dry_run or args.find_internships):
        lock = SingleInstanceLock()
        if not lock.acquire():
            print(f"[!] Another instance of Myth Job Watcher is already running. Exiting immediately to prevent duplicate jobs.")
            sys.exit(0)

    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".watcher.pid")
    if not (args.once or args.dry_run or args.find_internships):
        try:
            with open(pid_file, "w", encoding="ascii") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

    db = None
    if not (args.dry_run or args.find_internships):
        db = init_database(DB_PATH)

    print("=== Myth ATS Job Watcher Started ===")
    print("Candidate:       Abhijeet Singh (B.Tech CSE Core, 2023-2027)")
    print("Target Roles:    Software Engineer, SDE, Java Developer, Backend (Spring Boot), Full-Stack, MTS")
    print("Internships:     Tech/Software Engineering Intern, SDE Intern, Backend/Frontend Intern (<= 72h)")
    print("Disqualifies:    Quality Engineer / QA / SDET, Firmware / Embedded, Hardware, Mechanical, Sales/HR")
    mode_str = (
        "Find Active Internships" if args.find_internships
        else "Dry Run (Preview Matches)" if args.dry_run
        else "Single pass" if args.once
        else f"Daemon Loop ({POLL_SECONDS}s)"
    )
    print(f"Mode:            {mode_str}")
    print(f"Max Job Age:     <= {args.max_age}h (Full-Time) | <= {MAX_INTERN_AGE_HOURS}h (Internships)")
    if TG_TOKEN and TG_CHAT:
        print(f"Telegram Bot:    Active (Chat ID: {TG_CHAT})")
    else:
        print("Telegram Bot:    Not configured (alerts will only print to console)")
    print("====================================\n")

    try:
        while True:
            poll_cycle(
                db,
                dry_run=args.dry_run,
                max_age=args.max_age,
                find_internships=args.find_internships,
            )
            if args.once or args.dry_run or args.find_internships:
                break
            print(f"\nSleeping for {POLL_SECONDS} seconds...\n")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nJob Watcher stopped by user.")
    finally:
        if not (args.once or args.dry_run or args.find_internships):
            if os.path.exists(pid_file):
                try:
                    os.remove(pid_file)
                except Exception:
                    pass
        if db:
            try:
                db.close()
            except Exception:
                pass
        if lock:
            lock.release()


if __name__ == "__main__":
    main()
