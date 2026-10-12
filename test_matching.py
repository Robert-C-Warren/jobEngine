import requests
import json
import feedparser
from bs4 import BeautifulSoup
import re

TARGET_TITLES = [
    "technical support", "imaging support", "tier 2", "tier 3", "tier ii", "tier iii",
    "pacs", "field service", "implementation specialist", "application support",
    "systems support", "support engineer", "customer support engineer", "l2 support", "l3 support",
    "integration specialist", "clinical support", "field engineer"
]

CLEARANCE_TERMS = [
    "clearance", "secret clearance", "top secret", "ts/sci", "ts-sci", "polygraph",
    "public trust", "dod", "department of defense", "usajobs", "defense contractor",
    "security clearance required", "active secret", "active top secret"
]

def is_clearance_or_gov(text: str) -> bool:
    t = text.lower()
    for term in CLEARANCE_TERMS:
        if re.search(r'\b' + re.escape(term) + r'\b', t):
            return True
    return False

def matches_title(title: str) -> bool:
    t = title.lower()
    return any(target in t for target in TARGET_TITLES)

def test_fetch_remoteok():
    print("--- RemoteOK ---")
    headers = {"User-Agent": "JobEngine/1.0"}
    r = requests.get("https://remoteok.com/api", headers=headers, timeout=10)
    data = r.json()
    matches = []
    for item in data[1:]: # first element is legal notice
        title = item.get("position", "")
        company = item.get("company", "")
        desc = item.get("description", "")
        location = item.get("location", "Remote")
        if matches_title(title) and not is_clearance_or_gov(title + " " + desc):
            matches.append((company, title, location, item.get("url", "")))
    print(f"RemoteOK: found {len(matches)} matching target titles")
    for m in matches[:5]:
        print(" ", m)

def test_fetch_jobicy():
    print("--- Jobicy ---")
    headers = {"User-Agent": "JobEngine/1.0"}
    r = requests.get("https://jobicy.com/api/v2/remote-jobs?count=50", headers=headers, timeout=10)
    data = r.json()
    matches = []
    for item in data.get("jobs", []):
        title = item.get("jobTitle", "")
        company = item.get("companyName", "")
        desc = item.get("jobDescription", "")
        location = item.get("jobGeo", "Remote")
        if matches_title(title) and not is_clearance_or_gov(title + " " + desc):
            matches.append((company, title, location, item.get("url", "")))
    print(f"Jobicy: found {len(matches)} matching target titles")
    for m in matches[:5]:
        print(" ", m)

def test_fetch_wwr():
    print("--- Weworkremotely ---")
    matches = []
    urls = [
        "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"
    ]
    for u in urls:
        f = feedparser.parse(u)
        for e in f.entries:
            title = e.title
            desc = e.description
            link = e.link
            if matches_title(title) and not is_clearance_or_gov(title + " " + desc):
                matches.append((title, link))
    print(f"WWR: found {len(matches)} matching target titles")
    for m in matches[:5]:
        print(" ", m)

if __name__ == "__main__":
    test_fetch_remoteok()
    test_fetch_jobicy()
    test_fetch_wwr()
