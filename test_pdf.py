from playwright.sync_api import sync_playwright
from pathlib import Path

def test_pdf():
    html_content = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 20px; color: #333; }
  h1 { color: #123456; text-align: center; margin-bottom: 4px; font-size: 24px; }
  .contact { text-align: center; color: #666; font-size: 13px; margin-bottom: 20px; }
</style>
</head>
<body>
  <h1>Robert Warren</h1>
  <div class="contact">Dayton, OH &bull; (626) 872-4171 &bull; robertcwarren1@gmail.com &bull; linkedin.com/in/robert-c-warren</div>
  <p>Test PDF generation</p>
</body>
</html>"""
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_content)
        out_path = Path("test_resume.pdf")
        page.pdf(path=str(out_path), format="Letter", margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"}, print_background=True)
        browser.close()
        print("PDF created successfully:", out_path.exists())

if __name__ == "__main__":
    test_pdf()
