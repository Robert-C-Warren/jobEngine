import requests

gh_companies = [
    "butterflynetwork", "relativity", "datadog", "gitlab", "elastic",
    "mongodb", "canonical", "twilio", "stripe", "komodohealth", "cockroachlabs",
    "pagerduty", "airtable", "figma"
]

TARGET_TERMS = [
    "support", "tier 2", "tier 3", "pacs", "imaging", "field service", "implementation",
    "application support", "technical support", "systems support", "escalation", "integration"
]

for comp in gh_companies:
    url = f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs?content=true"
    try:
        r = requests.get(url, headers={"User-Agent": "JobEngine/1.0"}, timeout=6)
        if r.status_code == 200:
            jobs = r.json().get("jobs", [])
            for j in jobs:
                title = j.get("title", "")
                loc = j.get("location", {}).get("name", "")
                if any(t in title.lower() for t in TARGET_TERMS):
                    print(f"GH [{comp}] {title} | Loc: {loc} | URL: {j.get('absolute_url')}")
    except Exception as e:
        pass
