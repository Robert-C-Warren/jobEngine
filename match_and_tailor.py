"""
match_and_tailor.py - ATS Resume Matching, Scoring & Asset Generation Engine.

Evaluates job listings in jobs.db using the Solutions Engineering Bridge rubric:
- 5 REQUIRED DNA pillars (+20 points each):
  1. B2B SaaS / Enterprise Software Environment
  2. Root-Cause Analysis (investigating complex bugs, reading logs: Event Viewer, CBS logs, Procmon, stack traces, reproducing issues)
  3. Database Interaction (SQL, SQL logs, database querying, data integrity troubleshooting)
  4. Engineering Escalation (working directly with QA, developers, or product teams on Tier 2/3 issues)
  5. Technical Stack (APIs, JSON, webhooks, cloud infrastructure, or client-server diagnostics)
- TRAP JOB PENALTIES (-50 points each; immediate rejection/0 if two or more are found):
  - Tier 1 IT Helpdesk or internal corporate IT support
  - Hardware troubleshooting, printer repair, or desktop provisioning
  - Active Directory administration or basic Office 365 password resets
  - High-volume inbound call center metrics
  - Pure SWE/SRE/DevOps or senior quota-carrying Pre-Sales roles
"""

import sys
import os
import re
import json
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
from evaluator import evaluate_job_description

MASTER_RESUME_FILE = ROOT_DIR / "master_resume.md"
RESUMES_DIR = ROOT_DIR / "outputs" / "resumes"
EMAILS_DIR = ROOT_DIR / "outputs" / "emails"
DAILY_MATCHES_FILE = ROOT_DIR / "daily_matches.md"

# Ensure output directories exist
RESUMES_DIR.mkdir(parents=True, exist_ok=True)
EMAILS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# REQUIRED DNA TAXONOMY (+20 points per pillar, max 100 points)
# ---------------------------------------------------------------------------
DNA_PILLARS = {
    "b2b_saas": {
        "label": "DNA 1: B2B SaaS / Enterprise Software",
        "points": 20.0,
        "terms": [
            "saas", "b2b", "software platform", "enterprise software", "cloud platform",
            "web application", "enterprise platform", "multi-tenant", "software product",
            "application platform", "clinical software", "diagnostic software", "data platform"
        ]
    },
    "root_cause_analysis": {
        "label": "DNA 2: Root-Cause Analysis & Log Triage",
        "points": 20.0,
        "terms": [
            "root cause", "root-cause", "rca", "event viewer", "windows event",
            "procmon", "process monitor", "sysinternals", "cbs log", "cbs logs",
            "log analysis", "reading logs", "analyze logs", "system logs", "application logs",
            "server logs", "error logs", "diagnostic logs", "stack trace", "stack traces",
            "crash dump", "memory dump", "reproduce", "reproducing", "bug reproduction",
            "complex bugs", "defect triage", "fault isolation", "registry tracing", "troubleshooting"
        ]
    },
    "database_interaction": {
        "label": "DNA 3: Database & SQL Interaction",
        "points": 20.0,
        "terms": [
            "sql", "sql server", "postgresql", "postgres", "mysql", "database querying",
            "sql logs", "query", "queries", "data integrity", "relational database",
            "database diagnostics", "schema", "deadlock", "query timeout", "data sync",
            "data synchronization", "stored procedure", "database troubleshooting"
        ]
    },
    "engineering_escalation": {
        "label": "DNA 4: Engineering & QA Escalation (Tier 2/3)",
        "points": 20.0,
        "terms": [
            "tier 2", "tier 3", "tier ii", "tier iii", "l2", "l3", "escalation", "escalations",
            "engineering team", "development team", "developers", "qa", "quality assurance",
            "product team", "product teams", "r&d", "bug report", "bug reports", "defect escalation",
            "jira", "escalate bugs", "escalating issues"
        ]
    },
    "technical_stack": {
        "label": "DNA 5: Technical Stack (APIs, JSON, Webhooks, Cloud)",
        "points": 20.0,
        "terms": [
            "api", "apis", "rest api", "restful", "json", "webhook", "webhooks",
            "postman", "sdk", "aws", "azure", "gcp", "cloud infrastructure", "python",
            "powershell", "hl7", "dicom", "pacs", "sftp", "etl", "data pipeline", "graphql"
        ]
    }
}

COMPILED_DNA_PILLARS = {
    pillar_key: {
        "label": pillar_data["label"],
        "points": pillar_data["points"],
        "patterns": [
            (term, re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE))
            for term in pillar_data["terms"]
        ]
    }
    for pillar_key, pillar_data in DNA_PILLARS.items()
}

# ---------------------------------------------------------------------------
# TRAP JOB PENALTIES (-50 points each; reject immediately if >= 2 found)
# ---------------------------------------------------------------------------
TRAP_RULES = [
    (
        "Tier 1 IT Helpdesk / Internal Corporate IT",
        [
            r"\btier\s*1\s+(?:it|help\s*desk|support)\b",
            r"\bl1\s+(?:it|help\s*desk)\b",
            r"\bhelp\s*desk\b",
            r"\binternal\s+it\b",
            r"\bcorporate\s+it\b",
            r"\bit\s+support\s+(?:specialist|engineer|analyst|technician)\b",
            r"\bit\s+systems\s+engineer\b",
            r"\bworkplace\s+technology\b",
            r"\bemployee\s+onboarding\s+and\s+offboarding\b"
        ]
    ),
    (
        "Hardware Troubleshooting / Printer Repair / Desktop Provisioning",
        [
            r"\bprinter\s+repair\b",
            r"\bprinters?\s+and\s+(?:copiers?|scanners?|peripherals?)\b",
            r"\bdesktop\s+provisioning\b",
            r"\blaptop\s+provisioning\b",
            r"\bdesktop\s+support\b",
            r"\bimaging\s+laptops\b",
            r"\bworkstation\s+setup\b",
            r"\bconference\s+room\s+av\b",
            r"\ba/v\s+equipment\b",
            r"\bbreak/fix\b"
        ]
    ),
    (
        "Active Directory Administration / Basic O365 Password Resets",
        [
            r"\bactive\s+directory\s+administration\b",
            r"\bpassword\s+resets?\b",
            r"\boffice\s*365\s+admin(?:istration)?\b",
            r"\bo365\s+admin(?:istration)?\b",
            r"\bgoogle\s+workspace\s+admin(?:istration)?\b",
            r"\baccount\s+lockouts?\b",
            r"\buser\s+provisioning\s+and\s+deprovisioning\b"
        ]
    ),
    (
        "High-Volume Inbound Call Center Metrics",
        [
            r"\bcall\s+center\b",
            r"\bsmile\s+on\s+the\s+phone\b",
            r"\bhigh-volume\s+inbound\s+calls?\b",
            r"\binbound\s+call\s+center\b",
            r"\baverage\s+handle\s+time\b",
            r"\bthis\s+is\s+not\s+your\s+role\b"
        ]
    ),
    (
        "Overshot Seniority / Pure DevOps-SRE / Quota-Carrying Pre-Sales",
        [
            r"\bsite\s+reliability\s+engineer\b",
            r"\bdevops\s+engineer\b",
            r"\bquota-carrying\b",
            r"\bcarry(?:ing)?\s+(?:a\s+)?(?:direct\s+)?(?:sales\s+)?quota\b",
            r"\bdirect\s+sales\s+quota\b",
            r"\bexceed\s+(?:our\s+)?sales\s+targets\b",
            r"\bmeet\s+or\s+exceed\s+(?:our\s+)?sales\s+(?:targets|quotas?)\b"
        ]
    )
]

COMPILED_TRAP_RULES = [
    (trap_name, [re.compile(pat, re.IGNORECASE) for pat in patterns])
    for trap_name, patterns in TRAP_RULES
]

# Title-level disqualifiers for immediate rejection
DISQUALIFIED_TITLE_PATTERNS = [
    re.compile(r"\b(help\s*desk|desktop\s+support|it\s+support|it\s+systems\s+engineer|corporate\s+it|internal\s+it|workplace\s+tech|endpoint\s+engineer|site\s+reliability|sre|devops|field\s+service)\b", re.IGNORECASE),
    re.compile(r"\b(principal|staff|director|vp|vice\s+president|head\s+of|chief)\b", re.IGNORECASE)
]

EXCLUSION_TERMS = [
    "security clearance", "secret clearance", "top secret", "ts/sci", "ts-sci",
    "polygraph", "public trust", "dod", "department of defense", "defense contractor",
    "usajobs", "military clearance", "cleared professional", "clearance required"
]

OHIO_TARGET_TERMS = ["dayton", "columbus", "cincinnati", "mason", "fairfield", "cleveland", "ohio"]

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


def parse_stored_evaluation(eval_raw: Any) -> Optional[Dict[str, Any]]:
    """Parse stored Gemini evaluation JSON if it uses the new recruiter schema."""
    if not eval_raw:
        return None
    try:
        data = json.loads(eval_raw) if isinstance(eval_raw, str) else eval_raw
        if isinstance(data, dict) and "score" in data and "reasoning" in data:
            return data
    except Exception:
        pass
    return None


def check_location_eligibility(location: str, title: str, description: str, salary_str: str) -> Tuple[bool, str]:
    """Verify job is either in Ohio or US Remote (and not onsite-only out of state)."""
    if not is_valid_location(location, title, description, salary_str):
        return (False, "Disqualified: Non-US, Versailles, or offshore location without US presence")

    combined_text = f"{title} {description}"
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
    if is_remote and not any(re.search(pat, loc_lower) for pat in [r"\bremote\b", r"\bvirtual\b", r"\bwork from home\b"]):
        if re.search(r"\b(?:onsite\s+\d+\s+days|onsite\s+three\s+days|hybrid\s+role\s+\(onsite|must\s+be\s+onsite|in-office\s+(?:tuesday|monday|wednesday|\d+\s+days))\b", desc_lower):
            if not re.search(r"\b(or\s+remote|remote\s+option|eligible\s+for\s+remote)\b", desc_lower):
                is_remote = False

    excludes_ohio = bool(re.search(r"\b(?:except|excluding|excludes|not eligible in|not open to)\b[^\.\n]*(?:ohio|\boh\b)", combined_text, re.IGNORECASE))

    if is_ohio:
        return (True, "Ohio Target Market")
    if is_remote and not excludes_ohio:
        return (True, "US Remote Eligible")
    return (False, "Disqualified: Out-of-state onsite/hybrid role without Ohio or US Remote option")


def calculate_match_score(job: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Compute job match score (0 to 100) using the 5 REQUIRED DNA (+20 each)
    and TRAP JOB PENALTIES (-50 each; immediate 0 if 2+ traps found).
    Uses stored Gemini evaluation when available, with deterministic DNA + Trap validation.
    """
    title = job.get("title", "")
    description = job.get("description", "")
    location = job.get("location", "")
    salary_str = job.get("salary_range", "")
    combined_text = f"{title} {description}"

    # 1. Hard Exclusions (Security Clearance / Government)
    for ex in EXCLUSION_TERMS:
        if re.search(r"\b" + re.escape(ex) + r"\b", combined_text, re.IGNORECASE):
            return (0.0, [f"Disqualified: Security clearance / government restriction ({ex})"])

    # 2. Hard Title Disqualifiers (Internal IT, Helpdesk, Desktop Support, SRE, Executive/Principal)
    for pat in DISQUALIFIED_TITLE_PATTERNS:
        m = pat.search(title)
        if m:
            return (0.0, [f"Trap Title Rejected: '{m.group(0)}' in job title"])

    # 3. Location Eligibility (Ohio or US Remote)
    loc_ok, loc_reason = check_location_eligibility(location, title, description, salary_str)
    if not loc_ok:
        return (0.0, [loc_reason])

    # 4. Salary Ceiling Guard (> $195k indicates overshot Principal/Enterprise Quota/Staff role)
    max_sal = parse_max_salary_for_scoring(salary_str)

    # Clean boilerplate commission disclaimers before trap scanning
    cleaned_desc = description
    for bp in BOILERPLATE_PRESALES_PATTERNS:
        cleaned_desc = bp.sub("", cleaned_desc)
    scan_text = f"{title} {cleaned_desc}"

    # 5. Deterministic Trap Detection (-50 pts each; >= 2 traps = 0)
    detected_traps: List[str] = []
    for trap_name, patterns in COMPILED_TRAP_RULES:
        for pat in patterns:
            m = pat.search(scan_text)
            if m:
                detected_traps.append(f"{trap_name} ('{m.group(0)}')")
                break

    if max_sal > 195000:
        detected_traps.append(f"Salary ceiling exceeds $195k (${int(max_sal):,})")

    if len(detected_traps) >= 2:
        return (0.0, [f"Rejected (2+ Trap Flags): {', '.join(detected_traps)}"])

    # 6. Check if a new-schema Gemini evaluation is stored on the job
    stored_eval = parse_stored_evaluation(job.get("evaluation"))
    if stored_eval is not None:
        llm_score = float(stored_eval.get("score", 0))
        llm_reasoning = stored_eval.get("reasoning", "").strip()
        llm_traps = stored_eval.get("trap_flags") or []
        llm_blockers = stored_eval.get("tool_blockers") or []

        # Combine LLM traps with deterministic traps
        all_traps = list(llm_traps)
        for dt in detected_traps:
            if not any(dt.split(" (")[0].lower() in t.lower() for t in all_traps):
                all_traps.append(dt)

        if len(all_traps) >= 2:
            return (0.0, [f"Rejected by Trap Filter (2+ Traps): {', '.join(all_traps)}"])

        # Apply deterministic trap penalty if LLM missed a single deterministic trap
        if len(detected_traps) == 1 and len(llm_traps) == 0:
            llm_score = max(0.0, llm_score - 50.0)

        final_score = max(0.0, min(100.0, round(llm_score, 1)))
        reasons = [f"Recruiter Evaluation ({int(final_score)}/100): {llm_reasoning}"]
        if all_traps:
            reasons.append(f"Trap Flags (-50): {', '.join(all_traps)}")
        if llm_blockers:
            reasons.append(f"Tools / Blockers Required: {', '.join(llm_blockers)}")
        reasons.append(f"Location: {loc_reason}")
        return (final_score, reasons)

    # 7. Deterministic 5 REQUIRED DNA Scoring (+20 pts each)
    total_score = 0.0
    match_reasons: List[str] = []

    for pillar_key, pillar_data in COMPILED_DNA_PILLARS.items():
        matched_terms = []
        for term, pat in pillar_data["patterns"]:
            if pat.search(combined_text):
                matched_terms.append(term)
        if matched_terms:
            pts = pillar_data["points"]
            total_score += pts
            sample_terms = ", ".join(matched_terms[:4])
            match_reasons.append(f"{pillar_data['label']} ({sample_terms}) (+{int(pts)})")

    # Apply single trap penalty (-50 pts)
    if len(detected_traps) == 1:
        total_score = max(0.0, total_score - 50.0)
        match_reasons.append(f"Trap Penalty: {detected_traps[0]} (-50)")

    match_reasons.append(f"Location: {loc_reason}")
    final_score = max(0.0, min(100.0, round(total_score, 1)))
    return (final_score, match_reasons)


def sanitize_filename(text: str) -> str:
    """Create a safe filesystem filename."""
    clean = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", clean).strip("_")


BULLET_WEIGHT_TERMS = {
    "event viewer": 9.0, "procmon": 9.0, "cbs": 8.0, "sysinternals": 8.0,
    "sql": 8.0, "sql server": 8.0, "logs": 7.0, "root cause": 8.0,
    "reproduce": 7.0, "bug": 6.0, "tier 2": 6.0, "tier 3": 6.0,
    "escalation": 6.0, "qa": 5.0, "engineering": 5.0, "api": 6.0,
    "json": 5.0, "webhook": 5.0, "python": 5.0, "powershell": 5.0,
    "dicom": 6.0, "pacs": 6.0, "runbooks": 4.0, "sop": 4.0
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
    Generate an authentic, tailored PDF resume by reordering bullet points
    and customizing the summary and competency focus to match the job listing.
    """
    company = job.get("company", "Company")
    title = job.get("title", "Role")
    job_desc = job.get("description", "")
    full_job_context = f"{title} {job_desc}"

    # Midmark authentic software & log-diagnostics experience bullets
    midmark_bullets = [
        "Managed high-severity Tier 2/Tier 3 software escalations for clinical and enterprise imaging applications, isolating complex application crashes, installer failures, and OS-level faults using Windows Event Viewer, Procmon, and CBS logs.",
        "Conducted deep root-cause investigations into SQL Server runtime issues, analyzing SQL logs to resolve query timeouts, database connectivity drops, and data integrity/synchronization failures across client-server environments.",
        "Traced file-system mutations, registry keys, and background process activity with Sysinternals Procmon to reproduce elusive software defects and configuration conflicts.",
        "Partnered directly with software engineering and QA teams to escalate verified Tier 2/Tier 3 bugs with complete reproduction steps, Event Viewer/CBS log bundles, Procmon traces, and SQL execution logs to expedite patch releases.",
        "Engineered custom PowerShell and Python automation scripts to collect diagnostic logs, parse telemetry outputs, and deploy configuration fixes, cutting recurring incident resolution times by 35%.",
        "Troubleshot application data workflows and DICOM/PACS integration pipelines, ensuring reliable data transmission and schema integrity across connected software platforms.",
        "Authored standardized technical runbooks and internal SOPs documenting complex log-triage workflows and workarounds, reducing escalation cycle times across the support organization."
    ]

    # Reorder bullets based on match with the specific job description
    scored_bullets = [(b, score_bullet_relevance(b, full_job_context)) for b in midmark_bullets]
    scored_bullets.sort(key=lambda x: x[1], reverse=True)
    sorted_midmark_bullets = [b[0] for b in scored_bullets]

    # Dynamically prioritize core competencies
    competencies = [
        ("Root-Cause Analysis & Log Diagnostics", "Windows Event Viewer, Sysinternals Suite (Procmon, Process Explorer), CBS Logs (Component-Based Servicing / installer & update diagnostics), Application & Crash Dump Analysis, Registry & File-System Tracing, Bug Reproduction.", 0.0),
        ("Database & Data Integrity Troubleshooting", "SQL Server (SQL Error Logs, Runtime Triage, Query Profiling, Execution Log Analysis, Deadlock & Timeout Troubleshooting), Relational Database Querying, Batch Data Synchronization, Schema Integrity.", 0.0),
        ("APIs, Integrations & Technical Stack", "REST APIs, JSON Payload Validation, Postman, Webhooks, Client-Server Architecture, DICOM/PACS Data Flow, TCP/IP, DNS, DHCP, VPNs.", 0.0),
        ("Engineering Escalation & Support Operations", "Tier 2 / Tier 3 Defect Triage, Engineering & QA Bug Escalation, Technical Runbooks, SOP Authoring, Client Onboarding, ServiceNow, Jira, Oracle Ticketing.", 0.0),
        ("Scripting & Development", "PowerShell, Python, SQL, Go, TypeScript, Node.js, Bash, Git.", 0.0)
    ]

    scored_comp = []
    for cat_name, cat_desc, _ in competencies:
        cat_score = score_bullet_relevance(cat_name + " " + cat_desc, full_job_context)
        scored_comp.append((cat_name, cat_desc, cat_score))
    scored_comp.sort(key=lambda x: x[2], reverse=True)

    summary = (
        f"High-performing Technical & Application Support Specialist with proven experience resolving complex Tier 2 / Tier 3 "
        f"software, database, and enterprise platform escalations. Deep expertise in log-driven root cause analysis (RCA) using "
        f"Windows Event Viewer, Procmon, CBS logs, and SQL Server logs to isolate bugs, verify data integrity, and escalate "
        f"reproducible defects to engineering teams. Averaged 35% reduction in ticket turnaround times through custom PowerShell "
        f"and Python automation. Positioned to deliver immediate impact for {company}'s {title} role."
    )

    base_name = f"{sanitize_filename(company)}_{sanitize_filename(title)}_resume"
    pdf_filepath = RESUMES_DIR / f"{base_name}.pdf"

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

    proof_point = (
        "In my recent role at Midmark Corporation, I managed complex Tier 2/Tier 3 software escalations across distributed "
        "client-server applications. I specialized in deep log-driven root cause analysis using Windows Event Viewer, Sysinternals "
        "Procmon, CBS logs, and SQL Server logs—reproducing elusive bugs, resolving database query timeouts and data sync issues, "
        "partnering directly with engineering/QA on defect escalations, and building PowerShell/Python automation scripts that "
        "reduced recurring ticket cycle times by 35%."
    )

    p1 = (
        f"I am writing to express my strong interest in the **{title}** role at **{company}**. With a proven track record "
        f"resolving high-tier software escalations, conducting log-level root cause analysis, and troubleshooting SQL database "
        f"and API data integrity, I am confident in my ability to immediately add value to your technical team."
    )

    p2 = proof_point

    p3 = (
        f"Given {company}'s focus on reliable software delivery and exceptional client outcomes, I would welcome the opportunity "
        f"to speak for 10–15 minutes about how my background in root-cause diagnostics, SQL/log triage, and cross-functional "
        f"engineering escalation can strengthen your team. My full resume is attached for your review, and I look forward to connecting.\n\n"
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
    1. Evaluates listings in SQLite using the 5 REQUIRED DNA & TRAP PENALTY rubric.
    2. Runs live Gemini Recruiter evaluation on top candidate pool if not yet evaluated with new schema.
    3. Builds fresh-only daily leaderboard (reported_date IS NULL or today).
    4. Enforces Max 2 Per Company cap on Top 10 slots.
    5. Generates PDF resume and cold email for Top 10 matches >= 60.
    6. Marks Top 10 as reported today (YYYY-MM-DD) and writes daily_matches.md.
    """
    print("\n" + "="*80)
    print("RESUME MATCHING & SOLUTIONS ENGINEERING BRIDGE PIPELINE")
    print("="*80)

    init_db()

    master_resume_text = load_master_resume()
    print(f"[*] Loaded Master Resume ({len(master_resume_text)} bytes)")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        jobs = [dict(r) for r in cursor.fetchall()]

    print(f"[*] Evaluating {len(jobs)} total jobs against Solutions Engineering Bridge rubric...")

    evaluated_jobs = []
    today_str = time.strftime("%Y-%m-%d")

    for job in jobs:
        # Sanitize salary if needed
        clean_sal = parse_and_validate_salary(job.get("description", ""), job.get("salary_range", "Not specified"))
        if clean_sal != job.get("salary_range"):
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE jobs SET salary_range = ? WHERE job_id = ?", (clean_sal, job["job_id"]))
                conn.commit()
            job["salary_range"] = clean_sal

        score, reasons = calculate_match_score(job)
        reasons_str = " | ".join(reasons)
        status = "matched" if score >= 60.0 else "rejected"

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

    # Identify fresh candidate pool (score >= 60, unreported or reported today)
    fresh_pool = [
        j for j in evaluated_jobs
        if (not j.get("reported_date") or j.get("reported_date") == today_str)
        and j["score"] >= 60.0
    ]
    fresh_pool.sort(key=lambda x: (x["score"], x.get("created_at", "")), reverse=True)

    # Ensure all candidates that could make the Top 10 are verified by Gemini's Recruiter prompt
    llm_verified_count = 0
    verified_top_count = 0
    verified_comp_counts: Dict[str, int] = {}

    for j in fresh_pool:
        comp = j["company"].strip()
        if verified_comp_counts.get(comp, 0) >= 2:
            continue

        if parse_stored_evaluation(j.get("evaluation")) is None and j.get("description"):
            try:
                eval_obj = evaluate_job_description(j["description"])
                eval_json = eval_obj.model_dump_json()
                j["evaluation"] = eval_json
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE jobs SET evaluation = ? WHERE job_id = ?", (eval_json, j["job_id"]))
                    conn.commit()
                # Re-score with Gemini evaluation now attached
                new_score, new_reasons = calculate_match_score(j)
                j["score"] = new_score
                j["status"] = "matched" if new_score >= 60.0 else "rejected"
                j["match_reasons"] = " | ".join(new_reasons)
                update_job_match(
                    job_id=j["job_id"],
                    score=j["score"],
                    status=j["status"],
                    match_reasons=j["match_reasons"],
                    resume_path=j.get("tailored_resume_path"),
                    email_path=j.get("cold_email_path")
                )
                llm_verified_count += 1
            except Exception as e:
                print(f"[!] Gemini verification skipped for '{j.get('title')}' ({j.get('company')}): {e}")

        if j["score"] >= 60.0 and j["status"] != "rejected":
            verified_comp_counts[comp] = verified_comp_counts.get(comp, 0) + 1
            verified_top_count += 1
            if verified_top_count >= 12:
                break

    if llm_verified_count > 0:
        print(f"[*] Gemini Recruiter LLM evaluated {llm_verified_count} candidate listings.")

    # Clear today's reported_date before assigning the final Top 10
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET reported_date = NULL WHERE reported_date = ?", (today_str,))
        conn.commit()
    for j in fresh_pool:
        if j.get("reported_date") == today_str:
            j["reported_date"] = None

    # Filter again after LLM verification
    fresh_candidates = [
        j for j in fresh_pool
        if j["score"] >= 60.0 and j["status"] != "rejected"
    ]
    fresh_candidates.sort(key=lambda x: (x["score"], x.get("created_at", "")), reverse=True)

    # Enforce "Max 2 Per Company" Cap on Top 10
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

    # Generate tailored assets and mark as reported for Top 10 matches
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

        mark_job_reported(j["job_id"], today_str)
        j["reported_date"] = today_str

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

    # Fetch archive jobs (last 7 days from prior dates, excluding today's Top 10, only keeping those still >= 60)
    top_job_ids = {j["job_id"] for j in top_matches}
    archived_jobs = [
        j for j in get_recently_reported_jobs(days=7, min_score=60.0)
        if j.get("reported_date") != today_str and j["job_id"] not in top_job_ids
    ]

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

    write_daily_matches_report(top_matches, archived_jobs)

    print(f"\n[+] Pipeline run complete:")
    print(f"    - Total Processed: {len(jobs)}")
    print(f"    - Fresh Unreported Candidates (>=60): {len(fresh_candidates)}")
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
        f"**Profile:** Robert Warren | B2B SaaS Technical Support, Integration & Product Analyst -> Solutions Engineering  ",
        f"**Filtering:** 5-Pillar DNA Rubric (+20 each) | Anti-Helpdesk / Anti-AD / Anti-Hardware Trap Penalties (-50 each)  ",
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
