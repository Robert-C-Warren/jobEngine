import requests

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

print("--- Testing Jobicy with tags ---")
for tag in ["technical-support", "supporting", "engineering", "devops"]:
    try:
        url = f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={tag}"
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            jobs = r.json().get("jobs", [])
            print(f"Jobicy [{tag}]: {len(jobs)} jobs")
            for j in jobs[:2]:
                print(f"  {j.get('jobTitle')} @ {j.get('companyName')} ({j.get('jobGeo')})")
    except Exception as e:
        print(f"Jobicy [{tag}] error: {e}")

print("--- Testing RemoteOK ---")
try:
    r = requests.get("https://remoteok.com/api", headers=headers, timeout=8)
    if r.status_code == 200:
        data = r.json()
        print(f"RemoteOK: {len(data)} total entries")
        count = 0
        for j in data[1:]:
            pos = j.get("position", "")
            if any(w in pos.lower() for w in ["support", "tier", "specialist", "service", "systems", "implementation"]):
                count += 1
                if count <= 4:
                    print(f"  {pos} @ {j.get('company')} ({j.get('location')})")
        print(f"RemoteOK matching: {count}")
except Exception as e:
    print(f"RemoteOK error: {e}")
