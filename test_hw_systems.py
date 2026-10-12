import requests

hardware_systems_companies = [
    "samsara", "verkada", "rubrik", "cohesity", "tanium", "sentinelone",
    "crowdstrike", "zscaler", "netskope", "nutanix", "purestorage",
    "illumina", "10xgenomics", "tempus", "benchling", "ro"
]

print("Testing enterprise hardware/systems/imaging companies:")
for c in hardware_systems_companies:
    try:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs", timeout=2)
        if r.status_code == 200:
            print(f"GH [{c}]: {len(r.json().get('jobs', []))} jobs")
    except Exception:
        pass
    try:
        r = requests.get(f"https://api.lever.co/v0/postings/{c}?mode=json", timeout=2)
        if r.status_code == 200:
            print(f"Lever [{c}]: {len(r.json())} jobs")
    except Exception:
        pass
