import re
from bs4 import BeautifulSoup
import requests

r = requests.get('https://boards-api.greenhouse.io/v1/boards/upstart/jobs?content=true')
data = r.json()
for j in data.get('jobs', []):
    if 'IT Support' in j['title']:
        raw_html = j.get('content', '')
        raw_html = raw_html.replace("&mdash;", " - ").replace("&ndash;", " - ").replace("—", " - ").replace("–", " - ")
        soup = BeautifulSoup(raw_html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

        pattern = r"(\$[\d,]+(?:\.\d{2})?\s*-\s*\$[\d,]+(?:\.\d{2})?(?:\s*(?:USD|per hour|/hr|/year|annually))?)"
        m = re.search(pattern, text)
        if m:
            print("Extracted Clean Salary Range:", m.group(1))
