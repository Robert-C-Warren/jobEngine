"""
match_and_tailor.py - ATS Resume Matching, Scoring & Asset Generation Engine.

Reads master_resume.md, evaluates unauthenticated scraped job listings in jobs.db,
extracts key technical requirements, computes ATS match scores (0-100),
filters roles, reorders resume bullets without fabricating experience,
generates tailored resumes and 3-paragraph cold outreach emails for roles >= 60,
outputs a terminal summary table, and writes daily_matches.md.
"""

import sys
import os
import re
import time
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# Add project root to path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))
from db import (
    get_connection, update_job_match, get_top_matches,
    init_db, mark_job_reported, get_recently_reported_jobs
)
from resume_exporter import export_resume_pdf
from fetch_jobs import parse_and_validate_salary, is_valid_location

MASTER_RESUME_FILE = ROOT_DIR / "master_resume.md"
RESUMES_DIR = ROOT_DIR / "outputs" / "resumes"
EMAILS_DIR = ROOT_DIR / "outputs" / "emails"
DAILY_MATCHES_FILE = ROOT_DIR / "daily_matches.md"

# Ensure output directories exist
RESUMES_DIR.mkdir(parents=True, exist_ok=True)
EMAILS_DIR.mkdir(parents=True, exist_ok=True)

# Keyword taxonomies with priority weights (Strict word boundaries)
PRIORITY_KEYWORDS = {
    # Tier 1: PACS, DICOM, Imaging & Medical Device Hardware (Top Priority)
    "imaging_pacs": {
        "weight": 35,
        "terms": [
            "pacs", "dicom", "imaging", "diagnostic imaging", "ultrasound",
            "modality", "sensor", "calibration", "medical device", "clinical systems",
            "radiology", "hl7", "healthtech", "biomedical", "medical software"
        ]
    },
    # Tier 2: Tier 2/3 Escalations, Root Cause Analysis & Low-Level Diagnostics
    "escalations_diagnostics": {
        "weight": 30,
        "terms": [
            "tier 2", "tier 3", "tier ii", "tier iii", "l2", "l3", "escalation",
            "root cause", "root cause analysis", "rca", "sysinternals", "process explorer",
            "procmon", "event viewer", "windows event", "crash dump", "memory dump",
            "fault isolation", "hardware diagnostics", "peripheral", "device driver",
            "drivers", "firmware", "usb", "libusbk", "registry tracing", "defect triage",
            "bug reproduction", "telemetry"
        ]
    },
    # Tier 3: Field Service, Implementation & Client Engineering
    "field_implementation": {
        "weight": 25,
        "terms": [
            "field service", "field engineer", "implementation specialist",
            "implementation consultant", "deployment", "rollout", "onboarding",
            "runbook", "sop", "client onboarding", "site deployment", "integration engineer",
            "solutions integration", "technical service"
        ]
    },
    # Tier 4: Database Diagnostics & Data Integrity
    "database_sql": {
        "weight": 15,
        "terms": [
            "sql server", "sql", "query profiling", "deadlock", "timeout",
            "database diagnostics", "stored procedure", "execution log",
            "relational database", "schema integrity", "data pipeline"
        ]
    },
    # Tier 5: Networking & Infrastructure
    "networking": {
        "weight": 15,
        "terms": [
            "tcp/ip", "dns", "dhcp", "vpn", "routing", "wireshark",
            "network trace", "packet analysis", "firewall", "lan/wan", "subnet"
        ]
    },
    # Tier 6: Identity, Access & IAM
    "identity_iam": {
        "weight": 12,
        "terms": [
            "active directory", "azure ad", "entra id", "sso", "saml",
            "mfa", "identity management", "iam", "access control", "user provisioning"
        ]
    },
    # Tier 7: Scripting, Automation & APIs
    "scripting_automation": {
        "weight": 12,
        "terms": [
            "powershell", "python", "scripting", "automation", "rest api",
            "api debugging", "postman", "telemetry", "payload validation", "log parsing"
        ]
    },
    # Tier 8: ITSM & Support Platforms
    "itsm_tooling": {
        "weight": 8,
        "terms": [
            "servicenow", "jira", "zendesk", "oracle ticketing", "ticketing",
            "incident resolution", "sla", "csat"
        ]
    },
    # Tier 9: Integration, APIs & Data Pipelines (FDE / Integration Primitives)
    "integration_data_pipeline": {
        "weight": 20,
        "terms": [
            "rest api", "restful", "webhook", "webhooks", "json", "data mapping",
            "data pipeline", "etl", "hl7", "fhir", "dicom", "pacs", "sftp",
            "postman", "workato", "mulesoft", "ipaas", "sdk", "llm", "agentic"
        ]
    }
}

# Compile keywords with strict word boundaries
COMPILED_PRIORITY_KEYWORDS = {
    cat_name: {
        "weight": cat_data["weight"],
        "patterns": [
            (term, re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE))
            for term in cat_data["terms"]
        ]
    }
    for cat_name, cat_data in PRIORITY_KEYWORDS.items()
}

TARGET_TITLES_ALIGNMENT = [
    "forward deployed engineer", "forward deployed", "fde",
    "deployment engineer", "deployment strategist",
    "solutions integration engineer", "solutions integration",
    "solutions engineer", "solutions architect", "solutions consultant", "solutions specialist",
    "integration engineer", "integrations engineer", "integration specialist",
    "implementation engineer", "implementation specialist", "implementation consultant",
    "technical account manager", "tam", "customer engineer", "partner engineer",
    "technical support specialist", "technical support engineer", "technical support",
    "support engineer", "support specialist", "application support specialist", "application support",
    "systems support specialist", "systems support", "systems engineer", "it systems engineer",
    "it support specialist", "it support analyst", "it support engineer", "desktop support",
    "technical escalations engineer", "technical escalation", "escalations engineer", "escalation engineer",
    "tier 2", "tier 3", "tier ii", "tier iii", "l2 support", "l3 support",
    "pacs support analyst", "pacs", "imaging support specialist", "imaging support",
    "clinical support", "clinical systems",
    "field service engineer", "field service", "field engineer", "field technician", "service engineer",
    "technical operations", "operations engineer", "site reliability engineer", "site reliability", "sre",
    "onboarding engineer", "technical onboarding",
    "customer support engineer", "customer support specialist", "client support engineer", "client support specialist"
]

# Sort titles by length descending so longer phrases match first, compiled with word boundaries
SORTED_TARGET_TITLES = sorted(TARGET_TITLES_ALIGNMENT, key=len, reverse=True)
COMPILED_TARGET_TITLES = [
    (target, re.compile(r"\b" + re.escape(target) + r"\b", re.IGNORECASE))
    for target in SORTED_TARGET_TITLES
]

EXCLUSION_TERMS = [
    "security clearance", "secret clearance", "top secret", "ts/sci", "ts-sci",
    "polygraph", "public trust", "dod", "department of defense", "defense contractor",
    "usajobs", "military clearance", "cleared professional", "clearance required"
]

# Culture red-flags for customer-service burnout / call-center cliches (-25 pts)
CULTURE_RED_FLAGS = [
    (re.compile(r"\bnot\s+(?:at\s+)?customer\s+relations\s+this\s+is\s+not\s+your\s+role\b", re.IGNORECASE), "Not customer relations / not your role"),
    (re.compile(r"\bthis\s+is\s+not\s+your\s+role\b", re.IGNORECASE), "This is not your role"),
    (re.compile(r"\bsmile\s+on\s+the\s+phone\b", re.IGNORECASE), "Smile on the phone"),
    (re.compile(r"\bcall\s+center\s+environment\b", re.IGNORECASE), "Call center environment"),
    (re.compile(r"\bcall\s+center\b", re.IGNORECASE), "Call center environment")
]

# Strict Ohio target locations (+20 pts)
OHIO_TARGET_TERMS = ["dayton", "columbus", "cincinnati", "mason", "fairfield", "cleveland", "ohio"]

# Explicit Remote target terms (+15 pts)
REMOTE_TARGET_TERMS = ["remote", "anywhere", "work from home", "virtual", "distributed"]

# Seniority cap patterns (-15 pts for executive/staff level or > $195k salary ceiling)
EXECUTIVE_SENIORITY_PATTERN = re.compile(r"\b(principal|staff|director|vp|head\s+of)\b", re.IGNORECASE)

# Pre-sales vs. Technical Implementation patterns (-20 pts)
STRONG_PRESALES_PATTERNS = [
    (re.compile(r"\bpre-sales\b", re.IGNORECASE), "pre-sales"),
    (re.compile(r"\bpresales\b", re.IGNORECASE), "presales"),
    (re.compile(r"\baccount\s+executives?\b", re.IGNORECASE), "account executive"),
    (re.compile(r"\bsales\s+cycles?\b", re.IGNORECASE), "sales cycle"),
    (re.compile(r"\brfps?\b", re.IGNORECASE), "RFP")
]
GENERIC_PRESALES_PATTERNS = [
    (re.compile(r"\bquotas?\b", re.IGNORECASE), "quota"),
    (re.compile(r"\bcommissions?\b", re.IGNORECASE), "commission")
]
BOILERPLATE_PRESALES_PATTERNS = [
    re.compile(r"\(for quota-based roles\)", re.IGNORECASE),
    re.compile(r"bonus or commission", re.IGNORECASE),
    re.compile(r"target commission amount", re.IGNORECASE),
    re.compile(r"base salary and target commission", re.IGNORECASE),
    re.compile(r"equal employment opportunity", re.IGNORECASE)
]

def parse_max_salary_for_scoring(salary_str: str) -> float:
    """Extract maximum annual salary from salary_range string, normalizing hourly rates to annual."""
    if not salary_str or salary_str == "Not specified":
        return 0.0
    nums = re.findall(r"\$?\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b", salary_str)
    vals = []
    for n in nums:
        clean_n = n.replace(",", "")
        try:
            val = float(clean_n)
            # If hourly (< 500), convert to annual based on 2080 hours
            if val < 500:
                val = val * 2080
            vals.append(val)
        except ValueError:
            pass
    return max(vals) if vals else 0.0

def load_master_resume(resume_path: Path = MASTER_RESUME_FILE) -> str:
    """Load text of master resume."""
    if not resume_path.exists():
        fallback = ROOT_DIR / "robert_warren_resume.md"
        if fallback.exists():
            return fallback.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Resume file not found at {resume_path}")
    return resume_path.read_text(encoding="utf-8")

def extract_job_keywords(text: str) -> Dict[str, List[str]]:
    """Extract matching technical keywords grouped by category from job text using strict word boundaries."""
    matched_categories = {}
    for cat_name, cat_data in COMPILED_PRIORITY_KEYWORDS.items():
        found = []
        for term, pattern in cat_data["patterns"]:
            if pattern.search(text):
                found.append(term)
        if found:
            matched_categories[cat_name] = found
    return matched_categories

def calculate_match_score(job: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Compute ATS match score from 0 to 100 based on technical keyword overlap.
    Returns (score, list_of_matching_reasons).
    """
    title = job.get("title", "")
    description = job.get("description", "")
    combined_text = f"{title} {description}"

    # Strict Exclusion Check
    for ex in EXCLUSION_TERMS:
        if re.search(r"\b" + re.escape(ex) + r"\b", combined_text, re.IGNORECASE):
            return (0.0, [f"Disqualified: Security clearance / government restriction ({ex})"])

    location = job.get("location", "")
    salary_str = job.get("salary_range", "")
    if not is_valid_location(location, title, description, salary_str):
        return (0.0, ["Disqualified: Non-US, Versailles, or offshore location without US presence"])

    match_reasons = []
    total_score = 0.0

    # 1. Target Title Alignment (Max 25 pts) - strict word boundaries
    title_points = 0.0
    for target, pat in COMPILED_TARGET_TITLES:
        if pat.search(title):
            title_points = 25.0
            match_reasons.append(f"Direct Title Match: '{target.title()}' (+25)")
            break
    if title_points == 0:
        # Partial title match using strict word boundaries
        partial_words = ["support", "specialist", "service", "implementation", "integration", "solutions", "deployment", "engineer", "analyst", "onboarding"]
        if any(re.search(r"\b" + w + r"\b", title, re.IGNORECASE) for w in partial_words):
            title_points = 15.0
            match_reasons.append("Partial Title Alignment (+15)")
    total_score += title_points

    # 2. Domain & Technical Keyword Overlap (Max 55 pts) - strict word boundaries
    extracted = extract_job_keywords(combined_text)
    domain_score = 0.0

    # Imaging & PACS (Top Priority, up to +35 pts)
    if "imaging_pacs" in extracted:
        pts = min(35.0, len(extracted["imaging_pacs"]) * 12.0)
        domain_score += pts
        match_reasons.append(f"Imaging/PACS Keywords ({', '.join(extracted['imaging_pacs'][:4])}) (+{int(pts)})")

    # Integration, API & Data Pipelines (Up to +10 pts)
    if "integration_data_pipeline" in extracted:
        pts = min(10.0, len(extracted["integration_data_pipeline"]) * 5.0)
        domain_score += pts
        match_reasons.append(f"Integration & Data Pipelines ({', '.join(extracted['integration_data_pipeline'][:4])}) (+{int(pts)})")

    # Tier 2/3 Escalations & Diagnostics (up to +30 pts)
    if "escalations_diagnostics" in extracted:
        pts = min(30.0, len(extracted["escalations_diagnostics"]) * 7.5)
        domain_score += pts
        match_reasons.append(f"Tier 2/3 RCA & Diagnostics ({', '.join(extracted['escalations_diagnostics'][:4])}) (+{int(pts)})")

    # Field Service & Implementation (up to +10 pts)
    if "field_implementation" in extracted:
        pts = min(10.0, len(extracted["field_implementation"]) * 8.0)
        domain_score += pts
        match_reasons.append(f"Field Service & Implementation ({', '.join(extracted['field_implementation'][:3])}) (+{int(pts)})")

    # Database & SQL (up to +15 pts)
    if "database_sql" in extracted:
        pts = min(15.0, len(extracted["database_sql"]) * 5.0)
        domain_score += pts
        match_reasons.append(f"Database/SQL Server Diagnostics ({', '.join(extracted['database_sql'][:3])}) (+{int(pts)})")

    # Networking (up to +15 pts)
    if "networking" in extracted:
        pts = min(15.0, len(extracted["networking"]) * 5.0)
        domain_score += pts
        match_reasons.append(f"Networking Protocols ({', '.join(extracted['networking'][:3])}) (+{int(pts)})")

    # Identity / IAM (up to +20 pts)
    if "identity_iam" in extracted:
        pts = min(20.0, len(extracted["identity_iam"]) * 4.0)
        domain_score += pts
        match_reasons.append(f"Active Directory / SSO / IAM ({', '.join(extracted['identity_iam'][:3])}) (+{int(pts)})")

    # Automation & Scripting (up to +25 pts)
    if "scripting_automation" in extracted:
        pts = min(25.0, len(extracted["scripting_automation"]) * 4.0)
        domain_score += pts
        match_reasons.append(f"Scripting & Automation ({', '.join(extracted['scripting_automation'][:3])}) (+{int(pts)})")

    # ITSM (up to +8 pts)
    if "itsm_tooling" in extracted:
        pts = min(8.0, len(extracted["itsm_tooling"]) * 4.0)
        domain_score += pts
        match_reasons.append(f"ITSM Platforms ({', '.join(extracted['itsm_tooling'][:2])}) (+{int(pts)})")

    # Cap domain score at 55
    total_score += min(55.0, domain_score)

    # 3. Location Alignment (Max 20 pts)
    # Strict Location Rule:
    # - +20 ONLY if explicitly contains Ohio targets (Dayton, Columbus, Cincinnati, Mason, Fairfield, OH, Ohio)
    # - +15 ONLY if explicitly contains remote indicators in location or description (and not excluding OH)
    # - Before applying Non-Local On-Site Penalty, inspect location AND description for remote indicators.
    loc_lower = location.lower()
    title_lower = title.lower()
    desc_lower = description.lower()

    is_ohio = (
        any(re.search(r"\b" + re.escape(loc) + r"\b", loc_lower) for loc in OHIO_TARGET_TERMS)
        or bool(re.search(r"\boh\b", loc_lower))
    ) and "versailles" not in loc_lower

    remote_indicators_loc = [
        r"\bremote\b", r"\bremotely\b", r"\bwork from home\b", r"\bvirtual\b",
        r"\bdistributed\b", r"\bdigital-first\b", r"\b#li-remote\b", r"\bwork from anywhere\b"
    ]
    remote_indicators_desc = [
        r"\bremote\b", r"\bremotely in the united states\b", r"\bremote in the u\.?s\.?\b",
        r"\bu\.?s\.? remote\b", r"\bremote - us\b", r"\bremote \(us\)\b",
        r"\bwork remotely from anywhere\b",
        r"\bwork from anywhere in the us\b", r"\bwork from anywhere in the u\.?s\.?\b",
        r"\bdigital-first\b", r"\b#li-remote\b", r"\bwork from home\b", r"\bvirtual\b",
        r"\b(?:fully\s+distributed|100%\s+distributed|distributed\s+(?:team|workforce|company|first|organization|culture))\b"
    ]
    is_remote = (
        any(re.search(pat, loc_lower) for pat in remote_indicators_loc)
        or any(re.search(pat, title_lower) for pat in remote_indicators_loc)
        or any(re.search(pat, desc_lower) for pat in remote_indicators_desc)
    )
    # If the role explicitly requires on-site presence without a remote option, do not treat as remote
    if is_remote and not any(re.search(pat, loc_lower) for pat in [r"\bremote\b", r"\bvirtual\b", r"\bwork from home\b"]):
        if re.search(r"\b(?:onsite\s+\d+\s+days|onsite\s+three\s+days|hybrid\s+role\s+\(onsite|must\s+be\s+onsite|in-office\s+(?:tuesday|monday|wednesday|\d+\s+days))\b", desc_lower):
            if not re.search(r"\b(or\s+remote|remote\s+option|eligible\s+for\s+remote)\b", desc_lower):
                is_remote = False

    excludes_ohio = bool(re.search(r"\b(?:except|excluding|excludes|not eligible in|not open to)\b[^\.\n]*(?:ohio|\boh\b)", combined_text, re.IGNORECASE))

    if is_ohio:
        total_score += 20.0
        match_reasons.append("Local Ohio Target Market (Dayton/Columbus/Cincinnati/Mason/Fairfield/OH) (+20)")
    elif is_remote and not excludes_ohio:
        total_score += 15.0
        match_reasons.append("Remote Target Location (+15)")
    else:
        # 0 location points and -25 Non-Local On-Site Penalty
        total_score = max(0.0, total_score - 25.0)
        match_reasons.append("Non-Local On-Site Penalty: Out-of-state role with no remote option (-25)")

    # 4. Seniority Cap (-15 pts)
    # Salary ceiling increased to $195,000 to accommodate CA/NYC upper pay bands.
    # Only trigger title-based seniority penalties on Principal, Staff, Director, VP, or Head of.
    # Do NOT penalize III, IV, or Senior on Support/Implementation/Integration/Solutions roles.
    max_sal = parse_max_salary_for_scoring(job.get("salary_range", ""))
    if EXECUTIVE_SENIORITY_PATTERN.search(title):
        total_score = max(0.0, total_score - 15.0)
        sal_note = f" (${int(max_sal):,})" if max_sal else ""
        match_reasons.append(f"Seniority Cap Penalty: Principal/Staff/Director/VP/Head of role{sal_note} (-15)")
    elif max_sal > 195000:
        total_score = max(0.0, total_score - 15.0)
        match_reasons.append(f"Seniority Cap Penalty: Salary ceiling exceeds $195k (${int(max_sal):,}) (-15)")
    elif re.search(r"\b(senior|iii|iv)\b", title, re.IGNORECASE):
        sal_str = f" (${int(max_sal):,})" if max_sal else ""
        match_reasons.append(f"Seniority Cap Exemption: Senior/III/IV technical role within band{sal_str}")

    # 5. Pre-Sales Quota-Carrying Penalty (-15 pts)
    # Only apply if description explicitly requires carrying a direct sales quota,
    # "exceed our sales targets", or "quota-carrying".
    # Do NOT penalize simply because text mentions "account executive" (e.g. post-sales handoff).
    quota_patterns = [
        re.compile(r"\bquota-carrying\b", re.IGNORECASE),
        re.compile(r"\bcarry(?:ing)?\s+(?:a\s+)?(?:direct\s+)?(?:sales\s+)?quota\b", re.IGNORECASE),
        re.compile(r"\bdirect\s+sales\s+quota\b", re.IGNORECASE),
        re.compile(r"\bassigned\s+(?:sales\s+)?quota\b", re.IGNORECASE),
        re.compile(r"\bexceed\s+(?:our\s+)?sales\s+targets\b", re.IGNORECASE),
        re.compile(r"\bmeet\s+or\s+exceed\s+(?:our\s+)?sales\s+(?:targets|quotas?)\b", re.IGNORECASE)
    ]
    has_quota_penalty = False
    quota_reason = ""
    if re.search(r"\b(pre-sales|presales)\b", title, re.IGNORECASE):
        has_quota_penalty = True
        quota_reason = "Title Pre-Sales"
    else:
        cleaned_desc = description
        for bp in BOILERPLATE_PRESALES_PATTERNS:
            cleaned_desc = bp.sub("", cleaned_desc)
        for q_pat in quota_patterns:
            m = q_pat.search(cleaned_desc)
            if m:
                has_quota_penalty = True
                quota_reason = m.group(0)
                break

    if has_quota_penalty:
        total_score = max(0.0, total_score - 15.0)
        match_reasons.append(f"Pre-Sales Quota Penalty: Requires direct sales quota / targets ({quota_reason}) (-15)")

    # 6. Culture Red-Flag Penalty (-25 pts)
    for flag_pat, flag_desc in CULTURE_RED_FLAGS:
        if flag_pat.search(combined_text):
            match_reasons.append(f"Culture Red-Flag Penalty: High-burnout / Call center cliches ({flag_desc}) (-25)")
            total_score = max(0.0, total_score - 25.0)
            break

    # Normalize to 0-100 range
    final_score = min(100.0, round(total_score, 1))
    return (final_score, match_reasons)

def sanitize_filename(text: str) -> str:
    """Create a safe filesystem filename."""
    clean = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", clean).strip("_")

BULLET_WEIGHT_TERMS = {
    "dicom": 10.0, "pacs": 10.0, "imaging": 8.0, "sensor": 6.0,
    "sysinternals": 7.0, "windows event viewer": 7.0, "crash dump": 7.0,
    "sql server": 6.0, "root cause": 6.0, "tier 2": 5.0, "tier 3": 5.0,
    "powershell": 5.0, "python": 5.0, "active directory": 5.0, "sso": 5.0,
    "vpn": 4.0, "networking": 4.0, "tcp/ip": 4.0, "servicenow": 4.0,
    "runbooks": 4.0, "sop": 4.0, "defect": 4.0, "hardware": 4.0
}

COMPILED_BULLET_WEIGHTS = [
    (term, re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE), w)
    for term, w in BULLET_WEIGHT_TERMS.items()
]

def score_bullet_relevance(bullet: str, job_text: str) -> float:
    """Calculate overlap score for a bullet point against the job requirements using strict word boundaries."""
    score = 0.0
    for term, pat, w in COMPILED_BULLET_WEIGHTS:
        if pat.search(job_text) and pat.search(bullet):
            score += w
    return score

def generate_tailored_resume(job: Dict[str, Any], extracted_reasons: List[str]) -> Path:
    """
    Generate an authentic, tailored markdown resume by reordering bullet points
    and customizing the summary and competency focus to match the job listing.
    """
    company = job.get("company", "Company")
    title = job.get("title", "Role")
    job_desc = job.get("description", "")
    full_job_context = f"{title} {job_desc}"

    # Midmark authentic experience bullets
    midmark_bullets = [
        "Managed high-severity Tier 2/Tier 3 technical escalations for clinical and diagnostic imaging software, isolating application crashes, driver conflicts, and OS faults using Sysinternals and Windows Event Viewer.",
        "Supported healthcare and dental imaging hardware/software ecosystems, troubleshooting digital sensor communication, peripheral connectivity (USB/IP), and DICOM/PACS data flow integrity.",
        "Conducted root-cause investigations into SQL Server runtime issues, resolving query timeouts, database connectivity drops, and batch data synchronization failures across distributed client-server environments.",
        "Handled identity and access management incidents across Active Directory and Entra ID (Azure AD), troubleshooting SAML/SSO token handshakes, security groups, and MFA configurations.",
        "Engineered custom PowerShell and Python automation scripts to collect diagnostic logs, parse telemetry outputs, and deploy configuration patches, cutting recurring incident resolution times by 35%.",
        "Partnered with software and hardware engineering teams to escalate reproducible bugs with complete crash dumps, network traces, and SQL execution plans to expedite patch releases.",
        "Authored standardized deployment blueprints, technical runbooks, and internal SOPs to document complex environment workarounds, reducing escalation cycle times across the team."
    ]

    # Reorder bullets based on match with the specific job description
    scored_bullets = [(b, score_bullet_relevance(b, full_job_context)) for b in midmark_bullets]
    scored_bullets.sort(key=lambda x: x[1], reverse=True)
    sorted_midmark_bullets = [b[0] for b in scored_bullets]

    # Dynamically prioritize core competencies
    competencies = [
        ("Imaging & Medical Devices", "Digital Imaging Systems, PACS & DICOM workflows, sensor calibration, medical/dental diagnostic software, peripheral hardware integration (USB/serial/IP devices), driver stack triage (libusbK, WinUSB).", 0.0),
        ("Operating Systems & Low-Level Diagnostics", "Windows Server, Windows 10/11, Sysinternals Suite (Process Explorer, Procmon), Windows Event Viewer, Crash Dump Analysis, peripheral enumeration, registry tracing, hardware/software fault isolation.", 0.0),
        ("Data Layers & Database Diagnostics", "SQL Server (Runtime Triage, Query Profiling, Execution Log Analysis, index checks, deadlock troubleshooting), REST API Debugging, Payload Validation, Schema Integrity.", 0.0),
        ("Networking & Identity / Access", "TCP/IP, DNS, DHCP, VPN configurations, corporate routing fundamentals, Wireshark packet analysis, Active Directory, Azure AD / Entra ID, SSO/SAML, MFA provisioning.", 0.0),
        ("Systems Scripting & Tooling", "PowerShell, Python, Go, SQL, TypeScript, Node.js, Bash, ServiceNow, Oracle Ticketing, Git, Postman.", 0.0),
        ("Field & Implementation Support", "Customer site escalation management, deployment blueprints, technical runbooks, client onboarding, root cause analysis (RCA) reporting, hardware replacement and firmware diagnostics.", 0.0)
    ]

    scored_comp = []
    for cat_name, cat_desc, _ in competencies:
        cat_score = score_bullet_relevance(cat_name + " " + cat_desc, full_job_context)
        scored_comp.append((cat_name, cat_desc, cat_score))
    scored_comp.sort(key=lambda x: x[2], reverse=True)

    # Tailored Professional Summary focusing on target domain
    summary = (
        f"High-performing Systems & Technical Support Specialist with proven experience resolving complex Tier 2 / Tier 3 "
        f"infrastructure, enterprise software, and diagnostic hardware escalations. Deep expertise in log-driven root cause "
        f"analysis (RCA), SQL Server database diagnostics, Windows OS internals, networking protocols, and system deployment. "
        f"Averaged 35% reduction in ticket turnaround times through custom PowerShell and Python automation. Positioned to deliver "
        f"immediate impact for {company}'s {title} role with dependable, high-satisfaction technical support and defect triage."
    )

    base_name = f"{sanitize_filename(company)}_{sanitize_filename(title)}_resume"
    pdf_filepath = RESUMES_DIR / f"{base_name}.pdf"

    # Export clean, ATS-compliant PDF resume directly using ReportLab
    export_resume_pdf(
        company=company,
        title=title,
        summary=summary,
        competencies=[(name, desc) for name, desc, _ in scored_comp],
        midmark_bullets=sorted_midmark_bullets,
        output_pdf_path=pdf_filepath
    )

    return pdf_filepath

def generate_cold_outreach_email(job: Dict[str, Any], score: float) -> Path:
    """
    Generate a concise, high-impact 3-paragraph cold outreach email
    specifically addressed to the hiring team for this role.
    """
    company = job.get("company", "Company")
    title = job.get("title", "the role")
    url = job.get("url", "")
    location = job.get("location", "Remote")

    # Tailored proof points based on company and title context
    proof_point = (
        "In my recent role at Midmark Corporation, I managed complex Tier 2/Tier 3 escalations across clinical hardware, "
        "diagnostic imaging systems, and distributed client-server applications. I specialized in log-driven root cause analysis "
        "using Sysinternals and Windows Event Viewer, resolved SQL Server runtime deadlocks and query timeouts, and built "
        "PowerShell/Python automation scripts that reduced recurring ticket cycle times by 35%."
    )

    p1 = (
        f"I am writing to express my strong interest in the **{title}** role at **{company}**. With a proven track record "
        f"resolving high-tier technical escalations, diagnosing software and peripheral hardware faults, and maintaining "
        f"enterprise data integrity, I am confident in my ability to immediately add value to your technical support operations."
    )

    p2 = proof_point

    p3 = (
        f"Given {company}'s focus on high-availability systems and exceptional client outcomes, I would welcome the opportunity "
        f"to speak for 10–15 minutes about how my background in root-cause diagnostics, systems scripting, and cross-functional "
        f"defect triage can strengthen your team. My full resume is attached for your review, and I look forward to connecting.\n\n"
        f"Best regards,\n\n"
        f"**Robert Warren**\n"
        f"Dayton, OH | (626) 872-4171 | robertcwarren1@gmail.com\n"
        f"[LinkedIn Profile](https://linkedin.com/in/robert-c-warren)"
    )

    email_content = f"""# Cold Outreach Email: {title} at {company}

**To:** Hiring Manager / Technical Talent Acquisition at {company}  
**Subject:** Application & Introduction: Robert Warren – {title}  
**Direct Application Link:** [{company} Job Posting]({url})  
**Target Location:** {location}  
**ATS Relevance Match:** {score}/100  

---

Dear {company} Hiring Team,

{p1}

{p2}

{p3}
"""
    filename = f"{sanitize_filename(company)}_{sanitize_filename(title)}_cold_email.md"
    filepath = EMAILS_DIR / filename
    filepath.write_text(email_content.strip(), encoding="utf-8")
    return filepath

def run_match_and_tailor() -> List[Dict[str, Any]]:
    """
    Main matching and tailoring pipeline:
    1. Evaluates listings in SQLite, updates scores with word boundaries & culture penalties.
    2. Builds fresh-only daily leaderboard (reported_date IS NULL).
    3. Enforces Max 2 Per Company cap on Top 10 slots.
    4. Generates PDF resume and cold email for Top 10 matches >= 60.
    5. Marks Top 10 as reported today (YYYY-MM-DD).
    6. Appends 7-day archive table to daily_matches.md.
    """
    print("\n" + "="*80)
    print("RESUME MATCHING & ATS TAILORING PIPELINE")
    print("="*80)

    # Initialize / migrate database schema
    init_db()

    # Verify master resume exists
    master_resume_text = load_master_resume()
    print(f"[*] Loaded Master Resume ({len(master_resume_text)} bytes)")

    # Fetch jobs to process
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        jobs = [dict(r) for r in cursor.fetchall()]

    print(f"[*] Evaluating {len(jobs)} total jobs against Robert Warren's profile...")

    evaluated_jobs = []
    matched_count = 0
    rejected_count = 0

    for job in jobs:
        score, reasons = calculate_match_score(job)
        reasons_str = " | ".join(reasons)

        # Sanitize salary if needed
        clean_sal = parse_and_validate_salary(job.get("description", ""), job.get("salary_range", "Not specified"))
        if clean_sal != job.get("salary_range"):
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE jobs SET salary_range = ? WHERE job_id = ?", (clean_sal, job["job_id"]))
                conn.commit()
            job["salary_range"] = clean_sal

        if score < 60.0:
            status = "rejected"
            rejected_count += 1
        else:
            status = "matched"
            matched_count += 1

        # Update database record
        update_job_match(
            job_id=job["job_id"],
            score=score,
            status=status,
            match_reasons=reasons_str,
            resume_path=job.get("tailored_resume_path"),
            email_path=job.get("cold_email_path")
        )

        job_copy = dict(job)
        job_copy["score"] = score
        job_copy["status"] = status
        job_copy["match_reasons"] = reasons_str
        evaluated_jobs.append(job_copy)

    today_str = time.strftime("%Y-%m-%d")

    # 1. Fresh-Only Daily Leaderboard Candidates:
    # Select jobs that have not been reported in past runs (or reported today in re-runs)
    # Excludes any jobs reported on prior dates (< today_str)
    fresh_candidates = [
        j for j in evaluated_jobs
        if (not j.get("reported_date") or j.get("reported_date") == today_str)
        and j["score"] >= 60.0 and j["status"] != "rejected"
    ]
    fresh_candidates.sort(key=lambda x: (x["score"], x.get("created_at", "")), reverse=True)

    # 2. Enforce "Max 2 Per Company" Cap:
    top_matches = []
    company_counts: Dict[str, int] = {}
    for j in fresh_candidates:
        comp = j["company"].strip()
        count = company_counts.get(comp, 0)
        if count < 2:
            company_counts[comp] = count + 1
            top_matches.append(j)
            if len(top_matches) == 10:
                break

    # 3. Generate tailored assets and mark as reported for Top 10 matches
    for j in top_matches:
        resume_path_str = j.get("tailored_resume_path") or ""
        email_path_str = j.get("cold_email_path") or ""

        if j["score"] >= 60.0:
            needs_resume = not resume_path_str or not (ROOT_DIR / resume_path_str).exists()
            needs_email = not email_path_str or not (ROOT_DIR / email_path_str).exists()

            if needs_resume or needs_email:
                pdf_path = generate_tailored_resume(j, j["match_reasons"].split(" | "))
                email_path = generate_cold_outreach_email(j, j["score"])
                resume_path_str = str(pdf_path.relative_to(ROOT_DIR)).replace("\\", "/")
                email_path_str = str(email_path.relative_to(ROOT_DIR)).replace("\\", "/")
                j["tailored_resume_path"] = resume_path_str
                j["cold_email_path"] = email_path_str

        # Mark as reported today
        mark_job_reported(j["job_id"], today_str)
        j["reported_date"] = today_str

        # Update DB with assets and reported_date
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE jobs
                SET reported_date = ?,
                    tailored_resume_path = ?,
                    cold_email_path = ?
                WHERE job_id = ?
            """, (today_str, resume_path_str if resume_path_str else None, email_path_str if email_path_str else None, j["job_id"]))
            conn.commit()

    # 4. Fetch archive jobs (last 7 days from prior dates, excluding today's Top 10)
    top_job_ids = {j["job_id"] for j in top_matches}
    archived_jobs = [
        j for j in get_recently_reported_jobs(days=7, min_score=60.0)
        if j.get("reported_date") != today_str and j["job_id"] not in top_job_ids
    ]

    # Ensure archived jobs with score >= 60 also have assets generated if previously omitted under old threshold
    for j in archived_jobs:
        if j["score"] >= 60.0:
            resume_path_str = j.get("tailored_resume_path") or ""
            email_path_str = j.get("cold_email_path") or ""
            needs_resume = not resume_path_str or not (ROOT_DIR / resume_path_str).exists()
            needs_email = not email_path_str or not (ROOT_DIR / email_path_str).exists()
            if needs_resume or needs_email:
                pdf_path = generate_tailored_resume(j, j["match_reasons"].split(" | "))
                email_path = generate_cold_outreach_email(j, j["score"])
                resume_path_str = str(pdf_path.relative_to(ROOT_DIR)).replace("\\", "/")
                email_path_str = str(email_path.relative_to(ROOT_DIR)).replace("\\", "/")
                j["tailored_resume_path"] = resume_path_str
                j["cold_email_path"] = email_path_str
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE jobs
                        SET tailored_resume_path = ?,
                            cold_email_path = ?
                        WHERE job_id = ?
                    """, (resume_path_str, email_path_str, j["job_id"]))
                    conn.commit()

    # Terminal Summary Table
    print("\n" + "-"*105)
    print(f"{'RANK':<5} | {'COMPANY':<18} | {'ROLE':<35} | {'LOCATION':<18} | {'SCORE':<5} | {'ASSETS'}")
    print("-" * 105)

    for idx, j in enumerate(top_matches, 1):
        comp = j['company'][:18]
        title = j['title'][:35]
        loc = j['location'][:18]
        score_str = f"{j['score']:.0f}"
        assets = "PDF Resume & Email" if j['score'] >= 60.0 else "Match (No assets)"
        print(f"{idx:<5} | {comp:<18} | {title:<35} | {loc:<18} | {score_str:<5} | {assets}")
    print("-" * 105)

    # Write daily_matches.md
    write_daily_matches_report(top_matches, archived_jobs)

    print(f"\n[+] Pipeline run complete:")
    print(f"    - Total Processed: {len(jobs)}")
    print(f"    - Fresh Unreported Candidates: {len(fresh_candidates)}")
    print(f"    - Top Fresh Matches Selected: {len(top_matches)} (Max 2 per company cap enforced)")
    print(f"    - Previously Reported Archive Roles: {len(archived_jobs)}")
    print(f"    - Output Report: daily_matches.md\n")

    return top_matches

def write_daily_matches_report(top_jobs: List[Dict[str, Any]], archived_jobs: Optional[List[Dict[str, Any]]] = None) -> None:
    """Generate daily_matches.md markdown summary report with fresh Top 10 and 7-day archive."""
    today_str = time.strftime('%Y-%m-%d %H:%M:%S')
    md = [
        "# Daily Job Matches & ATS Tailored Applications",
        f"**Generated:** {today_str}  ",
        f"**Profile:** Robert Warren | Systems & Technical Support Specialist | Dayton, OH / Remote  ",
        f"**Filtering:** Free Commercial Sources Only | Zero Security Clearance / Zero Government Roles  ",
        f"**Policy:** Fresh Matches Only (Unreported) | Max 2 Roles Per Company Cap  ",
        "",
        "---",
        "",
        "## Top 10 High-Relevance Opportunities (Fresh Matches)",
        "",
        "| Rank | Company | Title | Location | Score | Salary Range | Tailored Assets |",
        "| :---: | :--- | :--- | :--- | :---: | :--- | :--- |"
    ]

    if not top_jobs:
        md.append("| - | *No fresh unreported matches found today (>= 60)* | - | - | - | - | - |")
    else:
        for idx, j in enumerate(top_jobs, 1):
            if j.get('tailored_resume_path'):
                pdf_link = f"[Tailored PDF Resume]({j['tailored_resume_path']})"
                email_link = f"[Cold Email]({j['cold_email_path']})"
                assets_col = f"{pdf_link} · {email_link}"
            else:
                assets_col = "Below 60 threshold"
            salary = j.get('salary_range') or "Not specified"
            md.append(f"| {idx} | **{j['company']}** | [{j['title']}]({j['url']}) | {j['location']} | **{j['score']:.0f}/100** | {salary} | {assets_col} |")

    md.extend([
        "",
        "---",
        "",
        "## Detailed Role Breakdowns & Match Justifications",
        ""
    ])

    for idx, j in enumerate(top_jobs, 1):
        md.append(f"### {idx}. {j['title']} – {j['company']}")
        md.append(f"- **Direct Application URL:** [{j['url']}]({j['url']})")
        md.append(f"- **Location:** {j['location']}")
        md.append(f"- **Compensation:** {j.get('salary_range', 'Not specified')}")
        md.append(f"- **ATS Relevance Score:** **{j['score']:.0f} / 100**")
        md.append(f"- **Match Justification:** {j.get('match_reasons', 'N/A')}")
        if j.get('tailored_resume_path'):
            md.append(f"- **Tailored PDF Resume:** [{j['tailored_resume_path']}]({j['tailored_resume_path']})")
            md.append(f"- **Cold Outreach Email:** [{j['cold_email_path']}]({j['cold_email_path']})")
        md.append("")

    # Archive section
    if archived_jobs:
        md.extend([
            "---",
            "",
            "## Previously Reported High-Score Roles (Last 7 Days)",
            "",
            "| Date Reported | Company | Title | Location | Score | Compensation | Tailored Assets |",
            "| :---: | :--- | :--- | :--- | :---: | :--- | :--- |"
        ])
        for j in archived_jobs:
            rep_date = j.get("reported_date", "Prior")
            salary = j.get("salary_range") or "Not specified"
            if j.get("tailored_resume_path"):
                assets_col = f"[Resume]({j['tailored_resume_path']}) · [Email]({j['cold_email_path']})"
            else:
                assets_col = "Below 60 threshold"
            md.append(f"| {rep_date} | **{j['company']}** | [{j['title']}]({j['url']}) | {j['location']} | **{j['score']:.0f}/100** | {salary} | {assets_col} |")
        md.append("")

    DAILY_MATCHES_FILE.write_text("\n".join(md), encoding="utf-8")

if __name__ == "__main__":
    run_match_and_tailor()
