"""
match_and_tailor.py - ATS Resume Matching, Scoring & Asset Generation Engine.

Reads master_resume.md, evaluates unauthenticated scraped job listings in jobs.db,
extracts key technical requirements, computes ATS match scores (0-100),
filters roles, reorders resume bullets without fabricating experience,
generates tailored resumes and 3-paragraph cold outreach emails for roles >= 75,
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
from db import get_connection, update_job_match, get_top_matches
from resume_exporter import export_resume_docx, export_resume_pdf

MASTER_RESUME_FILE = ROOT_DIR / "master_resume.md"
RESUMES_DIR = ROOT_DIR / "outputs" / "resumes"
EMAILS_DIR = ROOT_DIR / "outputs" / "emails"
DAILY_MATCHES_FILE = ROOT_DIR / "daily_matches.md"

# Ensure output directories exist
RESUMES_DIR.mkdir(parents=True, exist_ok=True)
EMAILS_DIR.mkdir(parents=True, exist_ok=True)

# Keyword taxonomies with priority weights
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
            "fault isolation", "hardware diagnostics", "peripheral", "driver", "usb",
            "libusbk", "registry tracing", "defect triage", "bug reproduction"
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
    }
}

TARGET_TITLES_ALIGNMENT = [
    "technical support specialist", "technical support engineer", "tier 2", "tier 3",
    "tier ii", "tier iii", "pacs support analyst", "imaging support specialist",
    "field service engineer", "implementation specialist", "implementation consultant",
    "solutions integration engineer", "technical escalations engineer",
    "systems support specialist", "application support specialist", "customer support engineer"
]

EXCLUSION_TERMS = [
    "security clearance", "secret clearance", "top secret", "ts/sci", "ts-sci",
    "polygraph", "public trust", "dod", "department of defense", "defense contractor",
    "usajobs", "military clearance", "cleared professional", "clearance required"
]

def load_master_resume(resume_path: Path = MASTER_RESUME_FILE) -> str:
    """Load text of master resume."""
    if not resume_path.exists():
        # Fallback to robert_warren_resume.md if master_resume.md not found
        fallback = ROOT_DIR / "robert_warren_resume.md"
        if fallback.exists():
            return fallback.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Resume file not found at {resume_path}")
    return resume_path.read_text(encoding="utf-8")

def extract_job_keywords(text: str) -> Dict[str, List[str]]:
    """Extract matching technical keywords grouped by category from job text."""
    text_lower = text.lower()
    matched_categories = {}
    for cat_name, cat_data in PRIORITY_KEYWORDS.items():
        found = []
        for term in cat_data["terms"]:
            pattern = r"\b" + re.escape(term) + r"\b"
            if re.search(pattern, text_lower):
                found.append(term)
        if found:
            matched_categories[cat_name] = found
    return matched_categories

def calculate_match_score(job: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Compute ATS match score from 0 to 100 based on technical keyword overlap.
    Returns (score, list_of_matching_reasons).
    """
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()
    combined_text = f"{title} {description}"

    # Strict Exclusion Check
    for ex in EXCLUSION_TERMS:
        if re.search(r"\b" + re.escape(ex) + r"\b", combined_text):
            return (0.0, [f"Disqualified: Security clearance / government restriction ({ex})"])

    location = job.get("location", "").lower()
    # Explicitly exclude Versailles per candidate preference
    if re.search(r"\bversailles\b", location) or re.search(r"\bversailles\b", combined_text):
        return (0.0, ["Disqualified: Versailles location excluded per candidate preference"])

    match_reasons = []
    total_score = 0.0

    # 1. Target Title Alignment (Max 25 pts)
    title_points = 0.0
    for target in TARGET_TITLES_ALIGNMENT:
        if target in title:
            title_points = 25.0
            match_reasons.append(f"Direct Title Match: '{target.title()}' (+25)")
            break
    if title_points == 0:
        # Partial title match
        if any(w in title for w in ["support", "specialist", "service", "implementation", "engineer", "analyst"]):
            title_points = 15.0
            match_reasons.append("Partial Title Alignment (+15)")
    total_score += title_points

    # 2. Domain & Technical Keyword Overlap (Max 55 pts)
    extracted = extract_job_keywords(combined_text)
    domain_score = 0.0

    # Imaging & PACS (Top Priority, up to +35 pts)
    if "imaging_pacs" in extracted:
        pts = min(35.0, len(extracted["imaging_pacs"]) * 12.0)
        domain_score += pts
        match_reasons.append(f"Imaging/PACS Keywords ({', '.join(extracted['imaging_pacs'][:4])}) (+{int(pts)})")

    # Tier 2/3 Escalations & Diagnostics (up to +30 pts)
    if "escalations_diagnostics" in extracted:
        pts = min(30.0, len(extracted["escalations_diagnostics"]) * 7.5)
        domain_score += pts
        match_reasons.append(f"Tier 2/3 RCA & Diagnostics ({', '.join(extracted['escalations_diagnostics'][:4])}) (+{int(pts)})")

    # Field Service & Implementation (up to +25 pts)
    if "field_implementation" in extracted:
        pts = min(25.0, len(extracted["field_implementation"]) * 8.0)
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

    # Identity / IAM (up to +12 pts)
    if "identity_iam" in extracted:
        pts = min(12.0, len(extracted["identity_iam"]) * 4.0)
        domain_score += pts
        match_reasons.append(f"Active Directory / SSO / IAM ({', '.join(extracted['identity_iam'][:3])}) (+{int(pts)})")

    # Automation & Scripting (up to +12 pts)
    if "scripting_automation" in extracted:
        pts = min(12.0, len(extracted["scripting_automation"]) * 4.0)
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
    if any(loc in location for loc in ["dayton", "cincinnati", "columbus", "cleveland", "ohio", "oh"]) and "versailles" not in location:
        total_score += 20.0
        match_reasons.append("Local Ohio Target Market (Dayton/Cincinnati/Columbus) (+20)")
    elif any(r in location for r in ["remote", "us-remote", "remote (us)", "united states", "usa"]):
        total_score += 15.0
        match_reasons.append("Remote / US Target Location (+15)")
    else:
        total_score += 10.0
        match_reasons.append("US Location Alignment (+10)")

    # Normalize to 0-100 range
    final_score = min(100.0, round(total_score, 1))
    return (final_score, match_reasons)

def sanitize_filename(text: str) -> str:
    """Create a safe filesystem filename."""
    clean = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", clean).strip("_")

def score_bullet_relevance(bullet: str, job_text: str) -> float:
    """Calculate overlap score for a bullet point against the job requirements."""
    b_lower = bullet.lower()
    j_lower = job_text.lower()
    score = 0.0

    # Key terms with high weighting
    weights = {
        "dicom": 10.0, "pacs": 10.0, "imaging": 8.0, "sensor": 6.0,
        "sysinternals": 7.0, "windows event viewer": 7.0, "crash dump": 7.0,
        "sql server": 6.0, "root cause": 6.0, "tier 2": 5.0, "tier 3": 5.0,
        "powershell": 5.0, "python": 5.0, "active directory": 5.0, "sso": 5.0,
        "vpn": 4.0, "networking": 4.0, "tcp/ip": 4.0, "servicenow": 4.0,
        "runbooks": 4.0, "sop": 4.0, "defect": 4.0, "hardware": 4.0
    }

    for term, w in weights.items():
        if term in j_lower and term in b_lower:
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

    # Format competencies block
    comp_lines = [f"- **{name}:** {desc}" for name, desc, _ in scored_comp]
    comp_block = "\n".join(comp_lines)

    # Tailored Professional Summary focusing on target domain
    summary = (
        f"High-performing Systems & Technical Support Specialist with proven experience resolving complex Tier 2 / Tier 3 "
        f"infrastructure, enterprise software, and diagnostic hardware escalations. Deep expertise in log-driven root cause "
        f"analysis (RCA), SQL Server database diagnostics, Windows OS internals, networking protocols, and system deployment. "
        f"Averaged 35% reduction in ticket turnaround times through custom PowerShell and Python automation. Positioned to deliver "
        f"immediate impact for {company}'s {title} role with dependable, high-satisfaction technical support and defect triage."
    )

    base_name = f"{sanitize_filename(company)}_{sanitize_filename(title)}_resume"
    md_filepath = RESUMES_DIR / f"{base_name}.md"
    docx_filepath = RESUMES_DIR / f"{base_name}.docx"
    pdf_filepath = RESUMES_DIR / f"{base_name}.pdf"

    content = f"""# Robert Warren
**Location:** Dayton, OH | **Phone:** (626) 872-4171 | **Email:** robertcwarren1@gmail.com | **LinkedIn:** linkedin.com/in/robert-c-warren
**Target Role:** {title} at {company}

---

## Professional Summary
{summary}

---

## Core Competencies & Technical Skills
{comp_block}

---

## Professional Experience

### Midmark Corporation | Versailles, OH
**Associate Technical Service Specialist** | *Jun 2024 – Sep 2026*
{chr(10).join(['- ' + b for b in sorted_midmark_bullets])}

### Quality Boat Salvage | Pasadena, CA
**Data & Operations Systems Specialist** | *Mar 2023 – Jun 2024*
- Architected automated inventory synchronization pipelines and data-handling scripts in Python, reducing sync cycle times by 20% while eliminating state desynchronization.
- Administered cloud directory accounts, access controls, multi-factor authentication (MFA), and data integrity standards across operational tools and databases.
- Authored operational runbooks, hardware maintenance guides, and system troubleshooting SOPs to standardize staff onboarding and operational technical procedures.

### Pyramid Consulting, Inc. | Remote / Los Angeles, CA
**IT Systems Engineer (Contract)** | *May 2022 – Nov 2022*
- Delivered enterprise L2/L3 systems support for distributed Windows and macOS endpoints, corporate VPNs, and AWS identity/access configurations.
- Triaged web application performance degradation, REST API failures, and runtime defects utilizing browser developer tools, HTTP request inspection, and server-side log output.
- Maintained a 95%+ first-contact satisfaction rating handling escalated technical tickets within enterprise ServiceNow environments.

---

## Technical Projects & Systems Engineering
- **Portsy – Distributed File Synchronization & State Engine** *(Go, Wails, TypeScript, Firestore)*: Built lightweight desktop background synchronization utility in Go utilizing OS file-system event listeners; engineered conflict-resolution algorithms for concurrent writes, file locks, and offline resilience.
- **EcoCommerce – Scalable Relational Data Platform & API Service** *(Node.js, TypeScript, React, Prisma, SQL)*: Designed full-stack platform with strictly typed relational schemas, query optimization, robust REST APIs, DNS management, and uptime monitoring.

---

## Education & Certifications
- **Associate of Science (AS), Computer Science** – Glendale Community College, Glendale, CA
- **Certificate in Digital Systems & Audio Engineering** – Icon Collective, Los Angeles, CA
"""

    # Write Markdown
    md_filepath.write_text(content.strip(), encoding="utf-8")

    # Export Word Document (.docx)
    export_resume_docx(
        company=company,
        title=title,
        summary=summary,
        competencies=[(name, desc) for name, desc, _ in scored_comp],
        midmark_bullets=sorted_midmark_bullets,
        output_docx_path=docx_filepath
    )

    # Export Adobe PDF (.pdf)
    export_resume_pdf(
        company=company,
        title=title,
        summary=summary,
        competencies=[(name, desc) for name, desc, _ in scored_comp],
        midmark_bullets=sorted_midmark_bullets,
        output_pdf_path=pdf_filepath
    )

    return pdf_filepath, docx_filepath, md_filepath

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
    Main matching and tailoring pipeline.
    Evaluates newly scraped listings in SQLite, updates scores, filters < 60,
    generates tailored assets for >= 75, outputs terminal summary, and writes daily_matches.md.
    """
    print("\n" + "="*80)
    print("RESUME MATCHING & ATS TAILORING PIPELINE")
    print("="*80)

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

        if score < 60.0:
            status = "rejected"
            rejected_count += 1
            resume_path_str = ""
            docx_path_str = ""
            email_path_str = ""
        else:
            status = "matched"
            matched_count += 1
            if score >= 75.0:
                # Generate tailored assets (PDF, Word Doc, Markdown)
                pdf_path, docx_path, md_path = generate_tailored_resume(job, reasons)
                email_path = generate_cold_outreach_email(job, score)
                resume_path_str = str(pdf_path.relative_to(ROOT_DIR)).replace("\\", "/")
                docx_path_str = str(docx_path.relative_to(ROOT_DIR)).replace("\\", "/")
                email_path_str = str(email_path.relative_to(ROOT_DIR)).replace("\\", "/")
            else:
                resume_path_str = ""
                docx_path_str = ""
                email_path_str = ""

        # Update database record
        update_job_match(
            job_id=job["job_id"],
            score=score,
            status=status,
            match_reasons=reasons_str,
            resume_path=resume_path_str if resume_path_str else None,
            email_path=email_path_str if email_path_str else None
        )

        job_copy = dict(job)
        job_copy["score"] = score
        job_copy["status"] = status
        job_copy["match_reasons"] = reasons_str
        job_copy["tailored_resume_path"] = resume_path_str
        job_copy["docx_path"] = docx_path_str
        job_copy["cold_email_path"] = email_path_str
        evaluated_jobs.append(job_copy)

    # Sort all by score descending
    evaluated_jobs.sort(key=lambda x: x["score"], reverse=True)

    # Terminal Summary Table
    print("\n" + "-"*105)
    print(f"{'RANK':<5} | {'COMPANY':<18} | {'ROLE':<35} | {'LOCATION':<18} | {'SCORE':<5} | {'ASSETS'}")
    print("-" * 105)

    top_matches = evaluated_jobs[:10]
    for idx, j in enumerate(top_matches, 1):
        comp = j['company'][:18]
        title = j['title'][:35]
        loc = j['location'][:18]
        score_str = f"{j['score']:.0f}"
        assets = "Resume & Email" if j['score'] >= 75.0 else ("Match (No assets)" if j['score'] >= 60 else "Filtered")
        print(f"{idx:<5} | {comp:<18} | {title:<35} | {loc:<18} | {score_str:<5} | {assets}")
    print("-" * 105)

    # Write daily_matches.md
    write_daily_matches_report(top_matches)

    print(f"\n[+] Pipeline run complete:")
    print(f"    - Total Processed: {len(jobs)}")
    print(f"    - Matched (Score >= 60): {matched_count}")
    print(f"    - Filtered Out (Score < 60): {rejected_count}")
    print(f"    - High Matches Tailored (Score >= 75): {sum(1 for j in evaluated_jobs if j['score'] >= 75.0)}")
    print(f"    - Output Report: daily_matches.md\n")

    return top_matches

def write_daily_matches_report(top_jobs: List[Dict[str, Any]]) -> None:
    """Generate daily_matches.md markdown summary report."""
    md = [
        "# Daily Job Matches & ATS Tailored Applications",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Profile:** Robert Warren | Systems & Technical Support Specialist | Dayton, OH / Remote  ",
        f"**Filtering:** Free Commercial Sources Only | Zero Security Clearance / Zero Government Roles  ",
        "",
        "---",
        "",
        "## Top 10 High-Relevance Opportunities",
        "",
        "| Rank | Company | Title | Location | Score | Salary Range | Tailored Assets |",
        "| :---: | :--- | :--- | :--- | :---: | :--- | :--- |"
    ]

    for idx, j in enumerate(top_jobs, 1):
        if j.get('tailored_resume_path'):
            pdf_link = f"[PDF Resume]({j['tailored_resume_path']})"
            docx_path_val = j.get('docx_path') or j['tailored_resume_path'].replace('.pdf', '.docx')
            docx_link = f"[Word Doc]({docx_path_val})"
            email_link = f"[Cold Email]({j['cold_email_path']})"
            assets_col = f"{pdf_link} · {docx_link} · {email_link}"
        else:
            assets_col = "Below 75 threshold"
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
            docx_path_val = j.get('docx_path') or j['tailored_resume_path'].replace('.pdf', '.docx')
            md.append(f"- **PDF Resume:** [{j['tailored_resume_path']}]({j['tailored_resume_path']})")
            md.append(f"- **Word Document (.docx):** [{docx_path_val}]({docx_path_val})")
            md.append(f"- **Cold Outreach Email:** [{j['cold_email_path']}]({j['cold_email_path']})")
        md.append("")

    DAILY_MATCHES_FILE.write_text("\n".join(md), encoding="utf-8")

if __name__ == "__main__":
    import time
    run_match_and_tailor()
