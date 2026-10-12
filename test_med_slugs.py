import requests

med_imaging_companies = [
    "enlitic", "subtlemedical", "flywheel", "quibim", "gleamer",
    "qmenta", "steris", "invacare", "radnet", "sectra",
    "infinitt", "nanox", "carestream", "hologic", "elekta", "varian",
    "agfa", "changehealthcare", "butterflynetwork", "heartflow",
    "cardinalhealth", "stryker", "olympus", "mindray", "covermymeds"
]

print("Checking medical/imaging companies on Greenhouse:")
for c in med_imaging_companies:
    try:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs", timeout=2)
        if r.status_code == 200:
            jobs = r.json().get("jobs", [])
            print(f"GH [{c}]: {len(jobs)} jobs")
    except Exception:
        pass

print("Checking medical/imaging companies on Lever:")
for c in med_imaging_companies:
    try:
        r = requests.get(f"https://api.lever.co/v0/postings/{c}?mode=json", timeout=2)
        if r.status_code == 200:
            jobs = r.json()
            print(f"Lever [{c}]: {len(jobs)} jobs")
    except Exception:
        pass
