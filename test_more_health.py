import requests

names = [
    "premierhealth", "clevelandclinic", "ohiohealth",
    "cincinnatichildrens", "nationwidechildrens", "cardinalhealth",
    "sectra", "carestream", "hologic", "radnet", "enlitic", 
    "subtlemedical", "infinitt", "heartflow", "nanox",
    "butterflynetwork", "omnicell", "dexcom", "epic", "symplr",
    "athenahealth", "healthcatalyst", "definitivehealthcare", "phreesia",
    "relativity", "covermymeds", "olive", "upstart", "rootinsurance",
    "medpace", "kroger", "cintas", "fifththird", "keybank", "sherwinwilliams"
]

for n in names:
    try:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{n}/jobs", timeout=2)
        if r.status_code == 200:
            print(f"GH [{n}]: {len(r.json().get('jobs', []))} jobs")
    except Exception:
        pass
    try:
        r = requests.get(f"https://api.lever.co/v0/postings/{n}?mode=json", timeout=2)
        if r.status_code == 200:
            print(f"Lever [{n}]: {len(r.json())} jobs")
    except Exception:
        pass
