from db import get_connection
import re

def extract_salary(text: str) -> str:
    pattern = r"(\$[\d,]+(?:\.\d{2})?(?:\s*(?:-|–|to)\s*\$[\d,]+(?:\.\d{2})?)?(?:\s*(?:/hr|/hour|per hour|/yr|/year|per year|annually))?)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    for m in matches:
        m_clean = m.strip()
        if m_clean.startswith("$") and len(m_clean) > 2:
            if "-" in m_clean or "to" in m_clean or any(s in m_clean.lower() for s in ["/hr", "/yr", "year", "hour", "annually"]) or len(m_clean) >= 6:
                return m_clean
    return "Not specified"

with get_connection() as conn:
    row = conn.execute("SELECT description FROM jobs WHERE company = 'Upstart'").fetchone()
    if row:
        print("Extracted salary for Upstart:", extract_salary(row["description"]))
        # Also print snippet where $ appears
        for m in re.finditer(r"\$[\d,]+", row["description"]):
            start = max(0, m.start() - 20)
            end = min(len(row["description"]), m.end() + 30)
            print("Snippet:", row["description"][start:end])
