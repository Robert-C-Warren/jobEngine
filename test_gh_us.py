import requests
from bs4 import BeautifulSoup
import re

GH_COMPANIES = [
    "butterflynetwork", "toast", "samsara", "verkada", "relativity",
    "datadog", "elastic", "mongodb", "okta", "canonical", "twilio",
    "stripe", "upstart", "doximity", "komodohealth", "purestorage",
    "tanium", "rubrik", "pagerduty", "cockroachlabs", "klaviyo"
]

NON_US_TERMS = [
    r"\bindia\b", r"\bind\b", r"\bbangalore\b", r"\bbengaluru\b", r"\bchennai\b", r"\bmumbai\b", r"\bpune\b", r"\bgurgaon\b", r"\bnoida\b", r"\bmohali\b",
    r"\bphilippines\b", r"\bmanila\b", r"\bsingapore\b", r"\bsgp\b", r"\bjapan\b", r"\btokyo\b", r"\bkorea\b", r"\bseoul\b",
    r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b", r"\buk\b", r"\blondon\b", r"\bireland\b", r"\bdublin\b",
    r"\bgermany\b", r"\bberlin\b", r"\bmunich\b", r"\bfrance\b", r"\bparis\b", r"\bspain\b", r"\bmadrid\b", r"\bbarcelona\b",
    r"\bcanada\b", r"\btoronto\b", r"\bvancouver\b", r"\bmontreal\b", r"\bmexico\b", r"\bcdmx\b", r"\bbrazil\b", r"\bsao paulo\b",
    r"\bcolombia\b", r"\bbogota\b", r"\bpoland\b", r"\bwarsaw\b", r"\bkrakow\b", r"\bnetherlands\b", r"\bamsterdam\b",
    r"\bcosta rica\b", r"\bportugal\b", r"\blisbon\b", r"\bitaly\b", r"\brome\b", r"\bmilan\b", r"\bsweden\b", r"\bswitzerland\b"
]

def is_non_us(text: str) -> bool:
    t = text.lower()
    return any(re.search(pat, t) for pat in NON_US_TERMS)

def is_us_or_ohio(text: str) -> bool:
    t = text.lower()
    valid = ["remote", "us", "usa", "united states", "ohio", "oh", "dayton", "cincinnati", "columbus", "nationwide"]
    return any(re.search(r"\b" + re.escape(v) + r"\b", t) for v in valid)

TARGETS = [
    "support", "tier 2", "tier 3", "tier ii", "tier iii", "pacs", "imaging",
    "field service", "implementation", "integration", "escalation", "specialist"
]

results = []
for c in GH_COMPANIES:
    url = f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            jobs = r.json().get("jobs", [])
            for j in jobs:
                title = j.get("title", "")
                loc = j.get("location", {}).get("name", "")
                comb = f"{title} {loc}"
                if is_non_us(comb):
                    continue
                if not is_us_or_ohio(loc):
                    continue
                if any(t in title.lower() for t in TARGETS):
                    results.append((c, title, loc, j.get("absolute_url")))
    except Exception:
        pass

print(f"Total verified US/Remote/Ohio roles from GH: {len(results)}")
for r in results[:20]:
    print(f"[{r[0]}] {r[1]} | Loc: {r[2]}")
