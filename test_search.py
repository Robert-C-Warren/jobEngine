import requests
from bs4 import BeautifulSoup
import urllib.parse

def test_ddg():
    query = 'site:boards.greenhouse.io ("Technical Support" OR "PACS" OR "Implementation Specialist" OR "Field Service")'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    r = requests.post('https://html.duckduckgo.com/html/', data={'q': query}, headers=headers, timeout=10)
    print("DDG POST status:", r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    links = soup.select('.result__url')
    snippets = soup.select('.result__snippet')
    titles = soup.select('.result__title')
    print(f"Found {len(links)} links, {len(titles)} titles")
    for t, l in zip(titles[:5], links[:5]):
        print(f"Title: {t.get_text(strip=True)} | URL: {l.get_text(strip=True)}")

if __name__ == '__main__':
    test_ddg()
