import requests
import json
from bs4 import BeautifulSoup
import re

GH_COMPANIES = [
    "butterflynetwork", "relativity", "toast", "okta", "datadog",
    "elastic", "mongodb", "canonical", "twilio", "stripe", "upstart",
    "doximity", "komodohealth", "brex", "figma", "klaviyo", "asana",
    "gusto", "pagerduty", "checkr", "carta", "cockroachlabs"
]

TARGET_KEYWORDS = [
    "technical support", "imaging", "tier 2", "tier 3", "tier ii", "tier iii",
    "pacs", "field service", "implementation", "support engineer",
    "systems support", "application support", "l2 support", "l3 support",
    "escalation", "integration engineer", "client support engineer"
]

EXCLUSION_KEYWORDS = [
    "clearance", "secret clearance", "top secret", "ts/sci", "ts-sci",
    "polygraph", "public trust", "dod", "department of defense",
    "usajobs", "defense contractor", "military clearance", "security clearance"
]

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text(separator=" ", strip=True)

def is_excluded(text: str) -> bool:
    t = text.lower()
    return any(re.search(r'\b' + re.escape(k) + r'\b', t) for k in EXCLUSION_KEYWORDS)

def is_target_title(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in TARGET_KEYWORDS)

def is_target_location(loc: str) -> bool:
    l = loc.lower()
    allowed = ["remote", "us", "united states", "nationwide", "anywhere", "ohio", "oh", "columbus", "cincinnati", "dayton"]
    return any(a in l for a in allowed)

jobs_found = []

print("Scanning Greenhouse boards...")
for comp in GH_COMPANIES:
    url = f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs?content=true"
    try:
        r = requests.get(url, headers={"User-Agent": "JobEngine/1.0"}, timeout=6)
        if r.status_code == 200:
            data = r.json()
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = j.get("location", {}).get("name", "Remote")
                desc = clean_html(j.get("content", ""))
                
                if is_target_title(title) and is_target_location(loc):
                    if not is_excluded(title + " " + desc):
                        jobs_found.append({
                            "source": f"Greenhouse ({comp})",
                            "company": comp.title(),
                            "title": title,
                            "location": loc,
                            "url": j.get("absolute_url"),
                            "desc_len": len(desc)
                        })
    except Exception as e:
        pass

print(f"Total matching jobs found from Greenhouse: {len(jobs_found)}")
for j in jobs_found[:10]:
    print(f"[{j['company']}] {j['title']} | {j['location']} | URL: {j['url']}")
