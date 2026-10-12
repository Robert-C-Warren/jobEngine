from fetch_jobs import fetch_greenhouse_jobs

jobs = fetch_greenhouse_jobs()
print("Total fetched from GH:", len(jobs))
for j in jobs:
    print(f"[{j['company']}] {j['title']} -- {j['location']}")
