import requests
import feedparser

feeds = [
    ("Adzuna RSS OH", "https://www.adzuna.com/search?q=Technical+Support&w=Ohio&format=rss"),
    ("WWR Support", "https://weworkremotely.com/categories/remote-customer-support-jobs.rss"),
    ("WWR DevOps", "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"),
    ("RemoteOK RSS", "https://remoteok.com/remote-jobs.rss"),
    ("Jobicy RSS", "https://jobicy.com/feed/")
]

for name, url in feeds:
    try:
        f = feedparser.parse(url)
        print(f"{name}: {len(f.entries)} entries, status: {getattr(f, 'status', 'N/A')}")
        if len(f.entries) > 0:
            print("  First entry:", f.entries[0].title)
    except Exception as e:
        print(f"{name} error: {e}")
