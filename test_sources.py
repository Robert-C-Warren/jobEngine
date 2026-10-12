"""Quick test script to check public job source connectivity and format."""
import requests
import feedparser

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

sources = [
    ("Jobicy API", "https://jobicy.com/api/v2/remote-jobs?count=20"),
    ("RemoteOK API", "https://remoteok.com/api"),
    ("WWR Support RSS", "https://weworkremotely.com/categories/remote-customer-support-jobs.rss"),
    ("WWR DevOps RSS", "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"),
    ("Arbeitnow API", "https://www.arbeitnow.com/api/job-board-api"),
    ("Greenhouse HeartFlow", "https://boards-api.greenhouse.io/v1/boards/heartflow/jobs"),
    ("Greenhouse Butterfly", "https://boards-api.greenhouse.io/v1/boards/butterflynetwork/jobs"),
]

for name, url in sources:
    try:
        if "rss" in url or "feed" in url:
            feed = feedparser.parse(url)
            print(f"{name}: Success, found {len(feed.entries)} entries")
        else:
            r = requests.get(url, headers=headers, timeout=8)
            print(f"{name}: Status {r.status_code}, length {len(r.text)}")
    except Exception as e:
        print(f"{name}: Error {e}")
