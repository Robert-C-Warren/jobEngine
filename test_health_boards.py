import requests

companies = [
    "medpace", "rootinsurance", "upstart", "covermymeds", "olive",
    "intelerad", "sectra", "terarecon", "novarad", "symplr",
    "definitivehealthcare", "healthcatalyst", "verily", "goodrx", "doximity",
    "omnicell", "hologic", "dexcom", "meridianbioscience", "cardinalhealth"
]

print("Checking Greenhouse boards:")
for c in companies:
    try:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs", timeout=4)
        if r.status_code == 200:
            print(f"GH [{c}]: {len(r.json().get('jobs', []))} jobs")
    except Exception:
        pass

print("Checking Lever boards:")
for c in companies:
    try:
        r = requests.get(f"https://api.lever.co/v0/postings/{c}?mode=json", timeout=4)
        if r.status_code == 200:
            print(f"Lever [{c}]: {len(r.json())} jobs")
    except Exception:
        pass
