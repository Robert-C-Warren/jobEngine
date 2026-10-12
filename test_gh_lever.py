import requests

gh_companies = [
    "butterflynetwork", "tempus", "veeva", "flatirondothealth", "modernizingmedicine",
    "omnicell", "komodohealth", "relativity", "datadog", "gitlab", "elastic",
    "postman", "mongodb", "grafana", "sentry", "pagerduty", "automattic", "canonical",
    "zapier", "cockroachlabs", "twilio", "stripe", "airtable", "figma"
]

lever_companies = [
    "tempus", "benchling", "ro", "athenahealth", "modernizingmedicine", "fullstory"
]

headers = {"User-Agent": "JobEngine/1.0"}

print("--- Testing Greenhouse Boards ---")
for comp in gh_companies:
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            print(f"GH [{comp}]: {len(jobs)} jobs")
        else:
            print(f"GH [{comp}]: HTTP {r.status_code}")
    except Exception as e:
        print(f"GH [{comp}]: {e}")

print("--- Testing Lever Boards ---")
for comp in lever_companies:
    try:
        url = f"https://api.lever.co/v0/postings/{comp}?mode=json"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            jobs = r.json()
            print(f"Lever [{comp}]: {len(jobs)} jobs")
        else:
            print(f"Lever [{comp}]: HTTP {r.status_code}")
    except Exception as e:
        print(f"Lever [{comp}]: {e}")
