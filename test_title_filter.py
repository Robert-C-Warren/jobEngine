import re

NON_TECH_TITLES = [
    r"\bsales\b", r"\bseller\b", r"\baccount executive\b", r"\brecruiter\b",
    r"\btalent acquisition\b", r"\bproduct designer\b", r"\bpayroll\b",
    r"\bbilling\b", r"\bmarketing\b", r"\bintern\b", r"\blegal\b",
    r"\bhuman resources\b", r"\bhr\b", r"\bfinance\b", r"\bcontent\b"
]

TECH_SUPPORT_TITLES = [
    r"\btechnical support\b", r"\btier 2\b", r"\btier 3\b", r"\btier ii\b", r"\btier iii\b",
    r"\bpacs\b", r"\bimaging support\b", r"\bfield service engineer\b", r"\bfield service\b",
    r"\bimplementation specialist\b", r"\bimplementation consultant\b",
    r"\bsupport engineer\b", r"\bsolutions integration engineer\b",
    r"\bintegration engineer\b", r"\btechnical escalation\b", r"\bescalation[s]? engineer\b",
    r"\bapplication support\b", r"\bsystems support\b", r"\bl2 support\b", r"\bl3 support\b",
    r"\bfield engineer\b", r"\bclinical support\b", r"\btechnical support engineer\b",
    r"\bcustomer support engineer\b", r"\bclient support engineer\b"
]

def is_valid_tech_job(title: str) -> bool:
    t = title.lower()
    for nt in NON_TECH_TITLES:
        if re.search(nt, t):
            return False
    return any(re.search(pat, t) for pat in TECH_SUPPORT_TITLES)

# Test cases
samples = [
    "Technical Support Specialist",
    "Tier 2 Technical Support Engineer",
    "Imaging Support Specialist",
    "PACS Support Analyst",
    "Field Service Engineer - Medical Systems",
    "Implementation Specialist",
    "Solutions Integration Engineer II",
    "Technical Escalations Engineer 2",
    "Specialist Seller - Connected Maintenance",
    "Senior Product Designer, Toast Support Experiences",
    "Billing Support Analyst",
    "Associate Talent Acquisition Partner"
]

for s in samples:
    print(f"'{s}' -> {is_valid_tech_job(s)}")
