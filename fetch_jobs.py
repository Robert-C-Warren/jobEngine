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
from db import init_db, insert_job, job_exists, generate_job_id, get_connection
from evaluator import evaluate_job_description

# Target profile criteria
TARGET_TITLE_PATTERNS = [
    r"\bforward deployed\b", r"\bfde\b", r"\bdeployment engineer\b", r"\bdeployment strategist\b",
    r"\bsolutions engineer\b", r"\bsolutions architect\b", r"\bsolutions consultant\b",
    r"\bsolutions integration\b", r"\bsolutions specialist\b",
    r"\bintegration engineer\b", r"\bintegrations engineer\b", r"\bintegration specialist\b",
    r"\bimplementation engineer\b", r"\bimplementation specialist\b", r"\bimplementation consultant\b",
    r"\btechnical account manager\b", r"\btam\b", r"\bcustomer engineer\b", r"\bpartner engineer\b",
    r"\btechnical support\b", r"\bsupport engineer\b", r"\bapplication support\b",
    r"\bsystems support\b", r"\bsystems engineer\b", r"\bit systems engineer\b",
    r"\btechnical escalation\b", r"\bescalation[s]? engineer\b",
    r"\btier 2\b", r"\btier 3\b", r"\btier ii\b", r"\btier iii\b", r"\bl2 support\b", r"\bl3 support\b",
    r"\bpacs\b", r"\bimaging support\b", r"\bclinical support\b", r"\bclinical systems\b",
    r"\bfield service\b", r"\bfield engineer\b", r"\bservice engineer\b",
    r"\btechnical operations\b", r"\boperations engineer\b", r"\bsite reliability\b", r"\bsre\b",
    r"\bonboarding engineer\b", r"\btechnical onboarding\b"
]

NON_TECH_PATTERNS = [
    r"\baccount executive\b", r"\brecruiter\b", r"\btalent acquisition\b",
    r"\bproduct designer\b", r"\bpayroll specialist\b", r"\bcontent writer\b",
    r"\blegal counsel\b", r"\bhuman resources\b", r"\bgraphic designer\b",
    r"\bmechanical\b", r"\bstructural\b", r"\bcivil\b", r"\bintern\b", r"\binternship\b",
    r"\buniversity graduate\b", r"\bnew grad\b"
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
    r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b", r"\buk\b", r"\bunited kingdom\b", r"\bgreat britain\b", r"\blondon\b", r"\bireland\b",
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
    "butterflynetwork", "tempus", "dexcom", "omadahealth", "zocdoc",
    "komodohealth", "doximity", "heartflow", "benchling",
    "flatiron", "hologic", "omnicell", "verily", "goodrx",
    "healthcatalyst", "medpace", "covermymeds",
    # Enterprise Hardware, IoT, Physical Security, Sensors, Logistics & Robotics
    "samsara", "verkada", "toast", "formlabs", "matterport", "skydio",
    "locusrobotics", "symbotic", "anduril", "flockfreight", "flexport",
    "purestorage", "tanium",
    # Enterprise Systems, Database, Infrastructure & Support
    "cloudflare", "datadog", "tailscale", "1password", "okta", "crowdstrike",
    "sentinelone", "rubrik", "braze", "plaid", "gusto",
    "relativity", "elastic", "mongodb", "canonical", "twilio", "stripe",
    "zscaler", "netskope", "pagerduty", "cockroachlabs", "hashicorp",
    "sentry", "grafana", "gitlab", "box", "notion", "airtable", "checkr",
    "ramp", "remote", "deel", "lattice", "rippling", "carta", "clearwave", "subsplash",
    # Support, Productivity & Developer Tooling
    "zapier", "automattic", "intercom", "freshworks", "confluent",
    "snowflake", "fastly",
    # Ohio-based & Remote Tech Leaders
    "upstart", "klaviyo", "brex", "asana", "figma", "rootinsurance",
    # Forward Deployed, Integration & Data Targets
    "databricks", "palantir", "scaleai", "anthropic", "fivetran", "dbt",
    "airbyte", "temporal", "launchdarkly", "postman", "workato", "mulesoft",
    "boomi", "trayio", "segment", "amplitude", "mixpanel", "linear",
    "redox", "zushealth", "canvasmedical", "iteratively"
]

LEVER_COMPANIES = [
    "heartbeathealth", "ro", "modernizingmedicine", "veeva", "shieldai",
    "athenahealth", "symplr", "scriptdrop",
    "palantir", "color", "includedhealth", "nominal", "kopperfield"
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

def parse_and_validate_salary(text: str, fallback: str = "Not specified") -> str:
    """
    Extracts and sanitizes salary information:
    - Never extracts funding metrics like $1M, $5B, ARR, ACV.
    - If parsed salary is < $35 (and not clearly an hourly rate like $43.70/hr), returns 'Not specified'.
    - Handles ranges with -, –, —, &mdash;, to.
    """
    candidate_str = ""
    if fallback and fallback != "Not specified":
        candidate_str = fallback
    else:
        candidate_str = text

    if not candidate_str or candidate_str == "Not specified":
        return "Not specified"

    # 1. Salary ranges (e.g. $70,000 - $110,000 USD or $43.70 — $53.94 USD or $85,000 to $105,000)
    range_regex = re.compile(
        r"(\$[\d,]+(?:\.\d{2})?\s*(?:[-–—]|to|&mdash;)\s*\$[\d,]+(?:\.\d{2})?(?:\s*(?:USD|per year|annually|/yr|/year|/hr|/hour|per hour))?)",
        re.IGNORECASE
    )
    for match in range_regex.finditer(candidate_str):
        m_str = match.group(1).strip()
        after = candidate_str[match.end():match.end()+15].lower()
        if re.match(r"^\s*(m|b|million|billion|arr|acv)", after):
            continue
        nums = [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+(?:\.\d{2})?)", m_str)]
        if not nums:
            continue
        is_hourly = any(h in m_str.lower() for h in ["/hr", "/hour", "per hour"]) or all(15 <= n <= 150 for n in nums)
        min_val = min(nums)
        if min_val < 35 and not is_hourly:
            continue
        if is_hourly and min_val < 15:
            continue
        return m_str

    # 2. Single amount with time unit (e.g. $120,000/year, $45.00/hour, $144,000 USD)
    single_unit_regex = re.compile(
        r"(\$[\d,]+(?:\.\d{2})?\s*(?:USD|per year|annually|/yr|/year|/hr|/hour|per hour))",
        re.IGNORECASE
    )
    for match in single_unit_regex.finditer(candidate_str):
        m_str = match.group(1).strip()
        after = candidate_str[match.end():match.end()+15].lower()
        if re.match(r"^\s*(m|b|million|billion|arr|acv)", after):
            continue
        nums = [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+(?:\.\d{2})?)", m_str)]
        if not nums:
            continue
        val = nums[0]
        is_hourly = any(h in m_str.lower() for h in ["/hr", "/hour", "per hour"])
        if val < 35 and not is_hourly:
            continue
        if is_hourly and val < 15:
            continue
        return m_str

    # 3. Standalone 5-6 digit amount >= 35,000
    standalone_regex = re.compile(r"(\$[\d,]{5,}(?:\.\d{2})?)")
    for match in standalone_regex.finditer(candidate_str):
        m_str = match.group(1).strip()
        after = candidate_str[match.end():match.end()+15].lower()
        if re.match(r"^\s*(m|b|million|billion|arr|acv|k\b)", after):
            continue
        nums = [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+(?:\.\d{2})?)", m_str)]
        if nums and nums[0] >= 35000:
            return m_str

    if candidate_str != text and text:
        return parse_and_validate_salary(text, "Not specified")

    return "Not specified"

def is_valid_location(location: str, title: str = "", description: str = "", salary: str = "") -> bool:
    comb_loc_title = f"{location} {title}".lower()

    # Explicitly exclude Versailles
    if re.search(r"\bversailles\b", comb_loc_title):
        return False

    explicit_us_markers = [
        r"\bunited states\b", r"\busa\b", r"\bu\.s\.\b", r"\bus\b", r"\bnationwide\b",
        r"\bohio\b", r"\boh\b", r"\bdayton\b", r"\bcincinnati\b",
        r"\bcolumbus\b", r"\bcleveland\b", r"\bmason\b", r"\bamericas\b", r"\bnorth america\b"
    ]
    has_explicit_us = any(re.search(p, comb_loc_title) for p in explicit_us_markers)

    # Only reject on NON_US_PATTERNS if the location doesn't ALSO explicitly include US/North America
    for pat in NON_US_PATTERNS:
        if re.search(pat, comb_loc_title):
            if not has_explicit_us:
                return False

    loc_clean = location.strip().lower()
    is_strictly_worldwide = bool(re.search(r"^(?:worldwide|anywhere|anywhere in the world)$", loc_clean)) or (
        ("worldwide" in loc_clean or "anywhere" in loc_clean) and not has_explicit_us
    )
    if is_strictly_worldwide:
        comb_full = f"{title} {description} {salary}".lower()
        has_us_presence = bool(re.search(r"\b(us only|u\.s\. only|north america|united states only|usa only)\b", comb_full))
        has_us_salary = bool(salary and salary != "Not specified" and ("$" in salary or "usd" in salary.lower())) or bool(re.search(r"\$[\d,]{4,}", description))
        if not (has_us_presence or has_us_salary):
            return False

    if has_explicit_us or re.search(r"\bremote\b", comb_loc_title):
        return True

    # Fallback: check description body for explicit US Remote eligibility when location header only lists hub cities
    if description:
        desc_lower = description.lower()
        if re.search(r"\b(remotely in the united states|remote in the u\.?s\.?|u\.?s\.? remote|remote - us|remote \(us\)|work remotely from anywhere in the u\.?s\.?)\b", desc_lower):
            return True

    return False

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

                metadata = j.get("metadata") or []
                raw_meta_sal = "Not specified"
                if isinstance(metadata, list):
                    for m in metadata:
                        if isinstance(m, dict) and "salary" in str(m.get("name", "")).lower():
                            raw_meta_sal = str(m.get("value", "Not specified"))

                salary = parse_and_validate_salary(desc_text, raw_meta_sal)

                if not is_valid_location(loc_name, title, desc_text, salary):
                    continue
                if is_excluded(desc_text + " " + title, comp):
                    continue

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

            salary = parse_and_validate_salary(desc_plain)

            if not is_valid_location(loc_name, title, desc_plain, salary):
                continue
            if is_excluded(desc_plain + " " + title, comp):
                continue

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

ASHBY_COMPANIES = [
    "cohere", "linear", "vanta", "retool", "posthog", "clay", "elevenlabs",
    "langchain", "pinecone", "supabase", "modal", "baseten", "anyscale",
    "replicate", "perplexity", "harvey", "glean", "decagon", "sardine",
    "middesk", "column", "unit", "merge", "paragon", "workos", "onebrief",
    "copia", "ramp", "abridge", "hippocraticai", "anterior", "ambiencehealthcare"
]

def fetch_single_ashby_board(comp: str) -> List[Dict[str, Any]]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{comp.strip()}?includeCompensation=true"
    listings = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        if r.status_code != 200:
            return listings
        jobs = r.json().get("jobs", [])
        for j in jobs:
            title = j.get("title", "")
            if not matches_target_profile(title):
                continue
            loc_name = j.get("location", "Remote") or "Remote"
            if j.get("isRemote") and "remote" not in loc_name.lower():
                loc_name = f"{loc_name} (Remote)"
            desc_plain = j.get("descriptionPlain", "") or clean_html(j.get("descriptionHtml", ""))
            comp_data = j.get("compensation") or {}
            raw_sal = comp_data.get("compensationTierSummary") or "Not specified"
            salary = parse_and_validate_salary(desc_plain, raw_sal)
            if not is_valid_location(loc_name, title, desc_plain, salary):
                continue
            if is_excluded(desc_plain + " " + title, comp):
                continue
            pub_date = str(j.get("publishedAt") or time.strftime("%Y-%m-%d"))[:10]
            listings.append({
                "company": comp.strip().title(),
                "title": title.strip(),
                "location": loc_name.strip() or "Remote",
                "salary_range": salary,
                "url": j.get("jobUrl", ""),
                "description": desc_plain,
                "date_posted": pub_date,
                "source": f"Ashby ({comp.strip()})"
            })
    except Exception:
        pass
    return listings

def fetch_ashby_jobs() -> List[Dict[str, Any]]:
    listings = []
    print(f"[*] Querying {len(ASHBY_COMPANIES)} Ashby company boards in parallel...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(fetch_single_ashby_board, ASHBY_COMPANIES):
            listings.extend(res)
    print(f"    -> Extracted {len(listings)} matching roles from Ashby boards.")
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

                raw_sal = j.get("salary") or "Not specified"
                salary = parse_and_validate_salary(desc, raw_sal)

                if not is_valid_location(loc, title, desc, salary):
                    continue
                if is_excluded(desc + " " + title, company):
                    continue

                pub_date = j.get("publication_date", time.strftime("%Y-%m-%d"))
                if pub_date and "T" in pub_date:
                    pub_date = pub_date.split("T")[0]

                listings.append({
                    "company": company.strip(),
                    "title": title.strip(),
                    "location": loc.strip() or "Remote",
                    "salary_range": salary,
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

                salary = parse_and_validate_salary(desc)

                if not is_valid_location(loc, title, desc, salary):
                    continue
                if is_excluded(desc + " " + title, company):
                    continue

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

                min_sal = j.get("annualSalaryMin")
                max_sal = j.get("annualSalaryMax")
                currency = j.get("salaryCurrency", "USD")
                if min_sal and max_sal:
                    raw_sal = f"${min_sal:,} - ${max_sal:,} {currency}"
                elif min_sal:
                    raw_sal = f"${min_sal:,}+ {currency}"
                else:
                    raw_sal = "Not specified"

                salary = parse_and_validate_salary(desc, raw_sal)

                if not is_valid_location(loc, title, desc, salary):
                    continue
                if is_excluded(desc + " " + title, company):
                    continue

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

                    sal_min = j.get("salary_min")
                    sal_max = j.get("salary_max")
                    if sal_min and sal_max:
                        raw_sal = f"${sal_min:,} - ${sal_max:,} USD"
                    else:
                        raw_sal = "Not specified"

                    salary = parse_and_validate_salary(desc, raw_sal)

                    if not is_valid_location(loc, title, desc, salary):
                        continue
                    if is_excluded(desc + " " + title, company):
                        continue

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

                salary = parse_and_validate_salary(raw_title + " " + desc)

                if not is_valid_location("Remote (US)", title, desc, salary):
                    continue
                if is_excluded(desc + " " + title, company):
                    continue

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
        fetch_ashby_jobs,
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
                # Pre-generate stable job_id to verify existence before calling LLM
                job_id = j.get("job_id") or generate_job_id(
                    j.get("company", ""),
                    j.get("title", ""),
                    j.get("url", "")
                )
                j["job_id"] = job_id

                # Only evaluate fresh listings to conserve API quota and avoid re-evaluating known duplicates
                if not job_exists(job_id):
                    desc = j.get("description", "")
                    if desc and desc.strip():
                        try:
                            eval_res = evaluate_job_description(desc)
                            j["evaluation"] = eval_res.model_dump() if eval_res else None
                        except Exception as eval_err:
                            print(f"[!] Evaluation failed for '{j.get('title', 'Unknown')}' ({j.get('company', 'Unknown')}): {eval_err}. Continuing with raw job.")
                            j["evaluation"] = None
                    else:
                        j["evaluation"] = None

                if insert_job(j):
                    new_inserted += 1
        except Exception as e:

            print(f"[!] Error in scraper {scraper.__name__}: {e}")

    # Database cleanup: sanitize any legacy salaries stored in jobs.db
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT job_id, salary_range, description FROM jobs WHERE salary_range IN ('$1', '$5', '$3', '$17')")
            bad_salaries = cursor.fetchall()
            for r in bad_salaries:
                clean_sal = parse_and_validate_salary(r["description"], r["salary_range"])
                cursor.execute("UPDATE jobs SET salary_range = ? WHERE job_id = ?", (clean_sal, r["job_id"]))
            conn.commit()
    except Exception as e:
        print(f"[!] Note: Database salary sanitization error: {e}")

    print("\n" + "="*60)
    print(f"JOB SOURCING RUN COMPLETED")
    print(f"Total matching roles identified: {total_found}")
    print(f"Newly inserted into SQLite (jobs.db): {new_inserted}")
    print("="*60 + "\n")
    return new_inserted

if __name__ == "__main__":
    aggregate_and_store_jobs()
