import requests
from bs4 import BeautifulSoup
import re

from fetch_jobs import matches_target_profile, is_valid_location, is_excluded, clean_html

companies = ["toast", "okta", "relativity", "upstart", "doximity", "komodohealth", "purestorage", "tanium"]

for comp in companies:
    url = f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs?content=true"
    r = requests.get(url, timeout=5)
    if r.status_code == 200:
        jobs = r.json().get("jobs", [])
        print(f"\n--- {comp} (total {len(jobs)} jobs) ---")
        for j in jobs:
            title = j.get("title", "")
            loc = j.get("location", {}).get("name", "Remote")
            if matches_target_profile(title):
                valid_loc = is_valid_location(loc, title)
                excl = is_excluded(clean_html(j.get("content", "")) + " " + title, comp)
                print(f"  Match Title: '{title}' | Loc: '{loc}' | Valid Loc: {valid_loc} | Excluded: {excl}")
