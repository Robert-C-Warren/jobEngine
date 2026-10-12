import urllib.parse
from playwright.sync_api import sync_playwright

def search_duckduckgo_playwright(query: str, max_results: int = 15):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        url = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}"
        try:
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            page.wait_for_selector("article, [data-testid='result']", timeout=6000)
            articles = page.query_selector_all("article, [data-testid='result']")
            for art in articles:
                title_elem = art.query_selector("h2 a, [data-testid='result-title-a']")
                snippet_elem = art.query_selector("[data-result='snippet'], .OgMakerbQqDYTuzLmsTwh")
                if title_elem:
                    href = title_elem.get_attribute("href")
                    title = title_elem.inner_text()
                    snippet = snippet_elem.inner_text() if snippet_elem else ""
                    if href and ("greenhouse.io" in href or "lever.co" in href):
                        results.append({"title": title, "url": href, "snippet": snippet})
                        if len(results) >= max_results:
                            break
        except Exception as e:
            print(f"Search error: {e}")
        finally:
            browser.close()
    return results

if __name__ == "__main__":
    q = 'site:boards.greenhouse.io ("Technical Support Specialist" OR "PACS" OR "Imaging" OR "Implementation Specialist")'
    print(f"Running search for: {q}")
    res = search_duckduckgo_playwright(q)
    print(f"Found {len(res)} results:")
    for r in res:
        print(f"  {r['title']} -> {r['url']}")
