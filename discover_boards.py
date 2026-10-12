import requests

candidates = [
    "butterflynetwork", "relativity", "datadog", "gitlab", "elastic",
    "mongodb", "canonical", "twilio", "stripe", "komodohealth",
    "upstart", "doximity", "ro", "benchling", "flatironhealth", "flatiron",
    "athenahealth", "healthcatalyst", "radnet", "intelerad", "sectra",
    "carestream", "hologic", "dexcom", "omnicell", "verily", "goodrx",
    "toast", "klaviyo", "gusto", "okta", "box", "asana", "notion",
    "lattice", "rippling", "hashicorp", "sentry", "grafana", "automattic",
    "zapier", "clearwave", "covermymeds", "rootinsurance", "medpace",
    "subsplash", "carta", "brex", "ramp", "remote", "deel", "gitlab",
    "pagerduty", "cockroachlabs", "airtable", "figma", "plaid", "checkr"
]

valid_gh = []
valid_lever = []

for c in candidates:
    try:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs", timeout=2)
        if r.status_code == 200:
            count = len(r.json().get("jobs", []))
            if count > 0:
                valid_gh.append((c, count))
    except Exception:
        pass
    try:
        r = requests.get(f"https://api.lever.co/v0/postings/{c}?mode=json", timeout=2)
        if r.status_code == 200:
            count = len(r.json())
            if count > 0:
                valid_lever.append((c, count))
    except Exception:
        pass

print("Valid Greenhouse:", len(valid_gh))
for c, cnt in sorted(valid_gh, key=lambda x: -x[1])[:20]:
    print(f"  GH {c}: {cnt} jobs")

print("Valid Lever:", len(valid_lever))
for c, cnt in sorted(valid_lever, key=lambda x: -x[1])[:20]:
    print(f"  Lever {c}: {cnt} jobs")
