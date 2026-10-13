"""
fetch_jobs.py - Autonomous Job Sourcing & Aggregation Engine.
Aggregates commercial job listings from free, unauthenticated feeds:
- Direct Greenhouse Enterprise Boards (Healthcare Imaging, IoT Hardware, Enterprise Systems)
- Direct Lever Boards
- Jobicy Public Remote API
- RemoteOK Public Remote API
- We Work Remotely (WWR) Public RSS Feeds
Strictly excludes all government jobs and jobs requiring security clearance.
Stores deduplicated listings in SQLite database (jobs.db).
"""

import sys
import os
import re
import time
import requests
import feedparser
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
from db import init_db, insert_job, job_exists, generate_job_id

# Target profile criteria
TARGET_TITLE_PATTERNS = [
    r"\btechnical support\b", r"\btier 2\b", r"\btier 3\b", r"\btier ii\b", r"\btier iii\b",
    r"\bpacs\b", r"\bimaging support\b", r"\bfield service\b", r"\bfield engineer\b",
    r"\bimplementation specialist\b", r"\bimplementation consultant\b",
    r"\bsupport engineer\b", r"\bsolutions integration engineer\b",
    r"\bintegration engineer\b", r"\btechnical escalation\b", r"\bescalation[s]? engineer\b",
    r"\bapplication support\b", r"\bsystems support\b", r"\bl2 support\b", r"\bl3 support\b",
    r"\bclinical support\b", r"\btechnical support engineer\b",
    r"\bcustomer support engineer\b", r"\bclient support engineer\b", r"\bsupport analyst\b",
    r"\bit support\b", r"\bit support specialist\b", r"\bit support analyst\b",
    r"\bit support engineer\b", r"\bdesktop support\b", r"\bsystems engineer\b",
    r"\bit systems engineer\b", r"\btechnical operations\b", r"\boperations systems\b",
    r"\bsolutions specialist\b", r"\bsolutions engineer\b", r"\bfield technician\b",
    r"\bservice engineer\b", r"\bclient support specialist\b", r"\bcustomer support specialist\b"
]

NON_TECH_PATTERNS = [
    r"\baccount executive\b", r"\brecruiter\b", r"\btalent acquisition\b",
    r"\bproduct designer\b", r"\bpayroll specialist\b", r"\bcontent writer\b",
    r"\blegal counsel\b", r"\bhuman resources business partner\b", r"\bgraphic designer\b"
]

# Strict negative keywords - Zero government or security clearance roles
EXCLUSION_KEYWORDS = [
    "security clearance", "secret clearance", "top secret", "ts/sci", "ts-sci",
    "polygraph", "public trust", "dod", "department of defense", "defense contractor",
    "usajobs", "military clearance", "cleared professional", "clearance required",
    "active secret", "active top secret", "ability to obtain a clearance",
    "us citizen eligible for clearance", "government clearance", "federal government",
    "air force base", "wright-patterson", "defense intelligence", "defense logistics"
]

EXCLUDED_COMPANIES = [
    "defense", "dod", "department of", "air force", "army", "navy",
    "lockheed", "raytheon", "booz allen", "general dynamics", "leidos",
    "caci", "saic", "northrop grumman", "brite", "mantech"
]

# Non-US location patterns to strictly filter out
NON_US_PATTERNS = [
    r"\bindia\b", r"\bind\b", r"\bbangalore\b", r"\bbengaluru\b", r"\bchennai\b", r"\bmumbai\b",
    r"\bpune\b", r"\bgurgaon\b", r"\bnoida\b", r"\bmohali\b", r"\bphilippines\b", r"\bmanila\b",
    r"\bsingapore\b", r"\bsgp\b", r"\bjapan\b", r"\btokyo\b", r"\bkorea\b", r"\bseoul\b",
    r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b", r"\buk\b", r"\blondon\b", r"\bireland\b",
    r"\bdublin\b", r"\bgermany\b", r"\bberlin\b", r"\bmunich\b", r"\bfrance\b", r"\bparis\b",
    r"\bspain\b", r"\bmadrid\b", r"\bbarcelona\b", r"\bcanada\b", r"\btoronto\b", r"\bvancouver\b",
    r"\bmontreal\b", r"\bmexico\b", r"\bcdmx\b", r"\bbrazil\b", r"\bcolombia\b", r"\bbogota\b",
    r"\bpoland\b", r"\bwarsaw\b", r"\bkrakow\b", r"\bnetherlands\b", r"\bcosta rica\b", r"\bportugal\b",
    r"\bitaly\b", r"\bsweden\b", r"\bswitzerland\b", r"\bestonia\b", r"\btallinn\b", r"\blatvia\b",
    r"\blithuania\b", r"\bisrael\b", r"\btaiwan\b", r"\bhong kong\b", r"\bdenmark\b", r"\bnorway\b",
    r"\bfinland\b", r"\baustria\b", r"\bbelgium\b", r"\bchile\b", r"\bargentina\b"
]

# Curated high-relevance enterprise companies
GREENHOUSE_COMPANIES = [
    # Clinical Imaging, HealthTech, Diagnostic Systems
    "butterflynetwork", "komodohealth", "doximity", "heartflow", "benchling",
    "flatiron", "hologic", "dexcom", "omnicell", "verily", "goodrx", "tempus",
    "healthcatalyst", "medpace", "covermymeds",
    # Enterprise Hardware, IoT, Physical Security, Sensors
    "toast", "samsara", "verkada", "purestorage", "tanium",
    # Enterprise Systems, Database, Infrastructure & Support
    "relativity", "datadog", "elastic", "mongodb", "okta",
    "canonical", "twilio", "stripe", "zscaler", "netskope",
    "rubrik", "pagerduty", "cockroachlabs", "hashicorp", "sentry", "grafana",
    "gitlab", "box", "notion", "airtable", "checkr", "plaid", "ramp", "remote",
    "deel", "lattice", "rippling", "carta", "clearwave", "subsplash",
    # Support, Productivity & Developer Tooling
    "zapier", "automattic", "intercom", "freshworks", "braze", "confluent",
    "snowflake", "fastly", "cloudflare",
    # Ohio-based & Remote Tech Leaders
    "upstart", "klaviyo", "brex", "asana", "gusto", "figma", "rootinsurance"
]

LEVER_COMPANIES = [
    "ro", "athenahealth", "modernizingmedicine", "symplr", "scriptdrop"
]

WWR_FEEDS = [
    ("We Work Remotely - Support", "https://weworkremotely.com/categories/remote-customer-support-jobs.rss"),
    ("We Work Remotely - DevOps/Systems", "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/xml, application/xml, text/html, */*"
}

import html

def clean_html(raw_html: Optional[str]) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not raw_html:
        return ""
    unescaped = html.unescape(raw_html)
    soup = BeautifulSoup(unescaped, "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()

def is_excluded(text: str, company: str = "") -> bool:
    """Strictly filter out government or security clearance roles."""
    comb = f"{text} {company}".lower()
    for term in EXCLUSION_KEYWORDS:
        if re.search(r"\b" + re.escape(term) + r"\b", comb):
            return True
    comp_lower = company.lower()
    for ec in EXCLUDED_COMPANIES:
        if ec in comp_lower:
            return True
    return False

def matches_target_profile(title: str) -> bool:
    """Check if title matches technical support and implementation categories and is not non-tech."""
    t = title.lower()
    for nt in NON_TECH_PATTERNS:
        if re.search(nt, t):
            return False
    return any(re.search(pat, t) for pat in TARGET_TITLE_PATTERNS)

def is_valid_location(location: str, title: str = "") -> bool:
    """Verify role is Remote, US-based, or within Ohio (Dayton, Cincinnati, Columbus). Strictly excludes Versailles."""
    comb = f"{location} {title}".lower()
    
    # Explicitly exclude Versailles per candidate preference
    if re.search(r"\bversailles\b", comb):
        return False

    for pat in NON_US_PATTERNS:
        if re.search(pat, comb):
            return False

    valid_patterns = [
        r"\bremote\b", r"\bunited states\b", r"\busa\b", r"\bus\b", r"\bnationwide\b",
        r"\banywhere\b", r"\bohio\b", r"\boh\b", r"\bdayton\b", r"\bcincinnati\b",
        r"\bcolumbus\b", r"\bcleveland\b", r"\bworldwide\b", r"\bamericas\b", r"\bnorth america\b"
    ]
    return any(re.search(p, comb) for p in valid_patterns)

def fetch_single_greenhouse_board(comp: str) -> List[Dict[str, Any]]:
    """Fetch matching jobs for a single Greenhouse board."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs?content=true"
    listings = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        if r.status_code != 200:
            return listings
        data = r.json()
        jobs = data.get("jobs", [])
        for j in jobs:
            try:
                title = j.get("title", "")
                loc_obj = j.get("location", {})
                loc_name = loc_obj.get("name", "Remote") if isinstance(loc_obj, dict) else "Remote"
                desc_html = j.get("content", "")
                desc_text = clean_html(desc_html)

                if not matches_target_profile(title):
                    continue
                if not is_valid_location(loc_name, title):
                    continue
                if is_excluded(desc_text + " " + title, comp):
                    continue

                metadata = j.get("metadata") or []
                salary = "Not specified"
                if isinstance(metadata, list):
                    for m in metadata:
                        if isinstance(m, dict) and "salary" in str(m.get("name", "")).lower():
                            salary = str(m.get("value", "Not specified"))

                if salary == "Not specified":
                    sal_match = re.search(r"\$[\d,]+(?:\.\d{2})?(?:\s*(?:-|–|—|to)\s*\$[\d,]+(?:\.\d{2})?)?(?:\s*(?:USD|per year|annually|/yr|/year|/hr|/hour|per hour))?", desc_text)
                    if sal_match:
                        salary = sal_match.group(0).strip()

                date_posted = j.get("updated_at") or time.strftime("%Y-%m-%d")

                listings.append({
                    "company": comp.replace("-", " ").title(),
                    "title": title.strip(),
                    "location": loc_name.strip() or "Remote",
                    "salary_range": salary,
                    "url": j.get("absolute_url", ""),
                    "description": desc_text,
                    "date_posted": str(date_posted),
                    "source": f"Greenhouse ({comp})"
                })
            except Exception:
                continue
    except Exception:
        pass
    return listings

def fetch_greenhouse_jobs() -> List[Dict[str, Any]]:
    """Fetch jobs from direct Greenhouse enterprise boards using parallel worker threads."""
    listings = []
    print(f"[*] Querying {len(GREENHOUSE_COMPANIES)} direct Greenhouse enterprise boards in parallel...")
    with ThreadPoolExecutor(max_workers=15) as executor:
        for res in executor.map(fetch_single_greenhouse_board, GREENHOUSE_COMPANIES):
            listings.extend(res)
    print(f"    -> Extracted {len(listings)} matching roles from Greenhouse boards.")
    return listings

def fetch_single_lever_board(comp: str) -> List[Dict[str, Any]]:
    """Fetch matching jobs for a single Lever board."""
    url = f"https://api.lever.co/v0/postings/{comp}?mode=json"
    listings = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        if r.status_code != 200:
            return listings
        jobs = r.json()
        if not isinstance(jobs, list):
            return listings
        for j in jobs:
            title = j.get("text", "")
            categories = j.get("categories", {})
            loc_name = categories.get("location", "Remote") or "Remote"
            desc_plain = j.get("descriptionPlain", "") or clean_html(j.get("description", ""))

            if not matches_target_profile(title):
                continue
            if not is_valid_location(loc_name, title):
                continue
            if is_excluded(desc_plain + " " + title, comp):
                continue

            sal_match = re.search(r"\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*(?:per year|annually|/yr|/year))?", desc_plain)
            salary = sal_match.group(0) if sal_match else "Not specified"

            created_at = j.get("createdAt")
            date_posted = time.strftime("%Y-%m-%d", time.gmtime(created_at / 1000)) if created_at else time.strftime("%Y-%m-%d")

            listings.append({
                "company": comp.title(),
                "title": title.strip(),
                "location": loc_name.strip() or "Remote",
                "salary_range": salary,
                "url": j.get("hostedUrl", ""),
                "description": desc_plain,
                "date_posted": date_posted,
                "source": f"Lever ({comp})"
            })
    except Exception:
        pass
    return listings

def fetch_lever_jobs() -> List[Dict[str, Any]]:
    """Fetch jobs from direct Lever company boards in parallel."""
    listings = []
    print(f"[*] Querying {len(LEVER_COMPANIES)} Lever company boards in parallel...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(fetch_single_lever_board, LEVER_COMPANIES):
            listings.extend(res)
    print(f"    -> Extracted {len(listings)} matching roles from Lever boards.")
    return listings

def fetch_remotive_jobs() -> List[Dict[str, Any]]:
    """Fetch jobs from Remotive free public remote API."""
    listings = []
    print("[*] Querying Remotive Free Public Remote API...")
    endpoints = [
        "https://remotive.com/api/remote-jobs?category=customer-support",
        "https://remotive.com/api/remote-jobs?category=devops",
        "https://remotive.com/api/remote-jobs?category=all-others"
    ]
    seen_urls = set()
    for endpoint in endpoints:
        try:
            r = requests.get(endpoint, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                continue
            jobs = r.json().get("jobs", [])
            for j in jobs:
                url = j.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = j.get("title", "")
                company = j.get("company_name", "Unknown")
                loc = j.get("candidate_required_location", "Remote (US)")
                desc = clean_html(j.get("description", ""))

                if not matches_target_profile(title):
                    continue
                if not is_valid_location(loc, title):
                    continue
                if is_excluded(desc + " " + title, company):
                    continue

                salary = j.get("salary") or "Not specified"
                pub_date = j.get("publication_date", time.strftime("%Y-%m-%d"))
                if pub_date and "T" in pub_date:
                    pub_date = pub_date.split("T")[0]

                listings.append({
                    "company": company.strip(),
                    "title": title.strip(),
                    "location": loc.strip() or "Remote",
                    "salary_range": salary.strip() if salary else "Not specified",
                    "url": url,
                    "description": desc,
                    "date_posted": pub_date or time.strftime("%Y-%m-%d"),
                    "source": "Remotive API"
                })
        except Exception:
            continue
    print(f"    -> Extracted {len(listings)} matching roles from Remotive API.")
    return listings

def fetch_arbeitnow_jobs() -> List[Dict[str, Any]]:
    """Fetch jobs from Arbeitnow free public API."""
    listings = []
    print("[*] Querying Arbeitnow Public API...")
    try:
        r = requests.get("https://www.arbeitnow.com/api/job-board-api", headers=HEADERS, timeout=8)
        if r.status_code == 200:
            jobs = r.json().get("data", [])
            for j in jobs:
                title = j.get("title", "")
                company = j.get("company_name", "Unknown")
                loc = j.get("location", "Remote")
                is_remote = j.get("remote", False)
                if is_remote and ("remote" not in loc.lower()):
                    loc = f"{loc} (Remote)"
                desc = clean_html(j.get("description", ""))
                url = j.get("url", "")

                if not matches_target_profile(title):
                    continue
                if not is_valid_location(loc, title):
                    continue
                if is_excluded(desc + " " + title, company):
                    continue

                sal_match = re.search(r"\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*(?:per year|annually|/yr|/year))?", desc)
                salary = sal_match.group(0) if sal_match else "Not specified"

                created_at = j.get("created_at")
                if isinstance(created_at, int):
                    date_posted = time.strftime("%Y-%m-%d", time.gmtime(created_at))
                else:
                    date_posted = str(created_at)[:10] if created_at else time.strftime("%Y-%m-%d")

                listings.append({
                    "company": company.strip(),
                    "title": title.strip(),
                    "location": loc.strip() or "Remote",
                    "salary_range": salary,
                    "url": url,
                    "description": desc,
                    "date_posted": date_posted,
                    "source": "Arbeitnow API"
                })
    except Exception:
        pass
    print(f"    -> Extracted {len(listings)} matching roles from Arbeitnow.")
    return listings

def fetch_jobicy_jobs() -> List[Dict[str, Any]]:
    """Fetch jobs from Jobicy public API."""
    listings = []
    print("[*] Querying Jobicy Free Remote API...")
    endpoints = [
        "https://jobicy.com/api/v2/remote-jobs?count=50&geo=usa",
        "https://jobicy.com/api/v2/remote-jobs?count=50&tag=supporting",
        "https://jobicy.com/api/v2/remote-jobs?count=50&tag=engineering"
    ]
    seen_urls = set()
    for endpoint in endpoints:
        try:
            r = requests.get(endpoint, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                continue
            data = r.json()
            jobs = data.get("jobs", [])
            for j in jobs:
                url = j.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = j.get("jobTitle", "")
                company = j.get("companyName", "Unknown")
                loc = j.get("jobGeo", "Remote, USA")
                desc = clean_html(j.get("jobDescription", ""))

                if not matches_target_profile(title):
                    continue
                if not is_valid_location(loc, title):
                    continue
                if is_excluded(desc + " " + title, company):
                    continue

                min_sal = j.get("annualSalaryMin")
                max_sal = j.get("annualSalaryMax")
                currency = j.get("salaryCurrency", "USD")
                if min_sal and max_sal:
                    salary = f"${min_sal:,} - ${max_sal:,} {currency}"
                elif min_sal:
                    salary = f"${min_sal:,}+ {currency}"
                else:
                    salary = "Not specified"

                listings.append({
                    "company": company.strip(),
                    "title": title.strip(),
                    "location": loc.strip() or "Remote, USA",
                    "salary_range": salary,
                    "url": url,
                    "description": desc,
                    "date_posted": j.get("pubDate", time.strftime("%Y-%m-%d")),
                    "source": "Jobicy API"
                })
        except Exception:
            continue
    print(f"    -> Extracted {len(listings)} matching roles from Jobicy API.")
    return listings

def fetch_remoteok_jobs() -> List[Dict[str, Any]]:
    """Fetch jobs from RemoteOK public API."""
    listings = []
    print("[*] Querying RemoteOK Free Public Endpoint...")
    try:
        r = requests.get("https://remoteok.com/api", headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 1:
                for j in data[1:]:
                    title = j.get("position", "")
                    company = j.get("company", "Unknown")
                    loc = j.get("location", "Remote")
                    desc = clean_html(j.get("description", ""))
                    url = j.get("url", "")

                    if not matches_target_profile(title):
                        continue
                    if not is_valid_location(loc, title):
                        continue
                    if is_excluded(desc + " " + title, company):
                        continue

                    sal_min = j.get("salary_min")
                    sal_max = j.get("salary_max")
                    if sal_min and sal_max:
                        salary = f"${sal_min:,} - ${sal_max:,} USD"
                    else:
                        sal_match = re.search(r"\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*(?:per year|annually|/yr|/year))?", desc)
                        salary = sal_match.group(0) if sal_match else "Not specified"

                    listings.append({
                        "company": company.strip(),
                        "title": title.strip(),
                        "location": loc.strip() or "Remote",
                        "salary_range": salary,
                        "url": url or f"https://remoteok.com/remote-jobs/{j.get('id', '')}",
                        "description": desc,
                        "date_posted": j.get("date", time.strftime("%Y-%m-%d")),
                        "source": "RemoteOK API"
                    })
    except Exception:
        pass
    print(f"    -> Extracted {len(listings)} matching roles from RemoteOK.")
    return listings

def fetch_wwr_jobs() -> List[Dict[str, Any]]:
    """Fetch jobs from We Work Remotely public RSS feeds."""
    listings = []
    print("[*] Parsing We Work Remotely Public RSS Feeds...")
    for feed_name, feed_url in WWR_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                raw_title = entry.get("title", "")
                if ":" in raw_title:
                    company, title = raw_title.split(":", 1)
                else:
                    company = "Unknown"
                    title = raw_title

                desc = clean_html(entry.get("description", "") or entry.get("summary", ""))
                url = entry.get("link", "")

                if not matches_target_profile(title):
                    continue
                if not is_valid_location("Remote (US)", title):
                    continue
                if is_excluded(desc + " " + title, company):
                    continue

                sal_match = re.search(r"\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*(?:per year|annually|/yr|/year|\+ Benefits))?", raw_title + " " + desc)
                salary = sal_match.group(0) if sal_match else "Not specified"

                listings.append({
                    "company": company.strip(),
                    "title": title.strip(),
                    "location": "Remote (US)",
                    "salary_range": salary,
                    "url": url,
                    "description": desc,
                    "date_posted": entry.get("published", time.strftime("%Y-%m-%d")),
                    "source": "WeWorkRemotely RSS"
                })
        except Exception:
            continue
    print(f"    -> Extracted {len(listings)} matching roles from We Work Remotely.")
    return listings

def aggregate_and_store_jobs() -> int:
    """Run all scrapers, filter duplicates, and persist into jobs.db."""
    init_db()
    total_found = 0
    new_inserted = 0

    sources = [
        fetch_greenhouse_jobs,
        fetch_lever_jobs,
        fetch_remotive_jobs,
        fetch_jobicy_jobs,
        fetch_arbeitnow_jobs,
        fetch_remoteok_jobs,
        fetch_wwr_jobs
    ]

    for scraper in sources:
        try:
            jobs = scraper()
            total_found += len(jobs)
            for j in jobs:
                if insert_job(j):
                    new_inserted += 1
        except Exception as e:
            print(f"[!] Error in scraper {scraper.__name__}: {e}")

    print("\n" + "="*60)
    print(f"JOB SOURCING RUN COMPLETED")
    print(f"Total matching roles identified: {total_found}")
    print(f"Newly inserted into SQLite (jobs.db): {new_inserted}")
    print("="*60 + "\n")
    return new_inserted

if __name__ == "__main__":
    aggregate_and_store_jobs()
