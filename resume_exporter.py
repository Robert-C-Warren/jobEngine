"""
resume_exporter.py - ATS-Compliant PDF Resume Generator for Job Engine.
Builds clean, single-column, executive-styled PDFs using ReportLab.
100% searchable vector text, standard ATS fonts, and clean page hierarchy.
"""

from pathlib import Path
from typing import List, Tuple
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, HRFlowable, PageBreak
)

def export_resume_pdf(
    company: str,
    title: str,
    summary: str,
    competencies: List[Tuple[str, str]],
    midmark_bullets: List[str],
    output_pdf_path: Path
) -> Path:
    """Generate a clean, single-column, ATS-compliant PDF resume using ReportLab."""
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    
    doc = SimpleDocTemplate(
        str(output_pdf_path),
        pagesize=letter,
        leftMargin=36,    # 0.5 in
        rightMargin=36,   # 0.5 in
        topMargin=36,     # 0.5 in
        bottomMargin=36   # 0.5 in
    )

    styles = getSampleStyleSheet()
    primary = colors.HexColor("#102C57")  # Deep Navy
    charcoal = colors.HexColor("#222222") # High-contrast body
    muted = colors.HexColor("#4A5568")    # Subtitle / metadata

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=18, leading=22,
        textColor=primary, alignment=1, spaceAfter=2
    )
    contact_style = ParagraphStyle(
        'Contact', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.8, leading=11.5,
        textColor=muted, alignment=1, spaceAfter=2
    )
    target_style = ParagraphStyle(
        'Target', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9.2, leading=12,
        textColor=primary, alignment=1, spaceAfter=7
    )
    section_style = ParagraphStyle(
        'SectionHeading', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=10.2, leading=13,
        textColor=primary, spaceBefore=6, spaceAfter=2, keepWithNext=True
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.8, leading=12,
        textColor=charcoal, spaceAfter=3
    )
    bullet_style = ParagraphStyle(
        'BulletText', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, leading=11.6,
        textColor=charcoal, leftIndent=12, firstLineIndent=-12, spaceAfter=2.5
    )
    job_header_style = ParagraphStyle(
        'JobHeader', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9.2, leading=12.5,
        textColor=charcoal, spaceBefore=4, spaceAfter=2, keepWithNext=True
    )
    p2_header_style = ParagraphStyle(
        'P2Header', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, leading=11,
        textColor=muted, alignment=2, spaceAfter=8
    )

    story = []

    # === PAGE 1 ===
    story.append(Paragraph("Robert Warren", title_style))
    contact_text = (
        'Dayton, OH &bull; (626) 872-4171 &bull; '
        '<a href="mailto:robertcwarren1@gmail.com"><font color="#102C57"><u>robertcwarren1@gmail.com</u></font></a> &bull; '
        '<a href="https://linkedin.com/in/robert-c-warren"><font color="#102C57"><u>linkedin.com/in/robert-c-warren</u></font></a> &bull; '
        '<a href="https://github.com/Robert-C-Warren"><font color="#102C57"><u>github.com/Robert-C-Warren</u></font></a>'
    )
    story.append(Paragraph(contact_text, contact_style))
    story.append(Paragraph(f"Target Role: {title} | {company}", target_style))

    # Professional Summary
    story.append(Paragraph("PROFESSIONAL SUMMARY", section_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=primary, spaceAfter=4))
    story.append(Paragraph(summary, body_style))

    # Core Competencies
    story.append(Paragraph("CORE COMPETENCIES & TECHNICAL SKILLS", section_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=primary, spaceAfter=4))
    for cat_name, cat_desc in competencies:
        story.append(Paragraph(f"&bull; <b>{cat_name}:</b> {cat_desc}", bullet_style))

    # Professional Experience
    story.append(Paragraph("PROFESSIONAL EXPERIENCE", section_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=primary, spaceAfter=4))

    story.append(Paragraph(
        "<b>Midmark Corporation</b> | Versailles, OH &mdash; <i>Associate Technical Service Specialist</i> (Jun 2024 &ndash; Sep 2026)",
        job_header_style
    ))
    for b in midmark_bullets:
        story.append(Paragraph(f"&bull; {b}", bullet_style))

    # Intentional clean page break between major appointments
    story.append(PageBreak())

    # === PAGE 2 ===
    story.append(Paragraph("Robert Warren &bull; (626) 872-4171 &bull; robertcwarren1@gmail.com &bull; Page 2", p2_header_style))

    story.append(Paragraph("PROFESSIONAL EXPERIENCE (CONTINUED)", section_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=primary, spaceAfter=4))

    story.append(Paragraph(
        "<b>Quality Boat Salvage</b> | Pasadena, CA &mdash; <i>Data & Operations Systems Specialist</i> (Mar 2023 &ndash; Jun 2024)",
        job_header_style
    ))
    qbs_bullets = [
        "Architected automated inventory synchronization pipelines and data-handling scripts in Python, reducing sync cycle times by 20% while eliminating state desynchronization.",
        "Administered cloud directory accounts, access controls, multi-factor authentication (MFA), and data integrity standards across operational tools and databases.",
        "Authored operational runbooks, hardware maintenance guides, and system troubleshooting SOPs to standardize staff onboarding and operational technical procedures."
    ]
    for b in qbs_bullets:
        story.append(Paragraph(f"&bull; {b}", bullet_style))

    story.append(Paragraph(
        "<b>Pyramid Consulting, Inc.</b> | Remote / Los Angeles, CA &mdash; <i>IT Systems Engineer (Contract)</i> (May 2022 &ndash; Nov 2022)",
        job_header_style
    ))
    pyr_bullets = [
        "Delivered enterprise L2/L3 systems support for distributed Windows and macOS endpoints, corporate VPNs, and AWS identity/access configurations.",
        "Triaged web application performance degradation, REST API failures, and runtime defects utilizing browser developer tools, HTTP request inspection, and server-side log output.",
        "Maintained a 95%+ first-contact satisfaction rating handling escalated technical tickets within enterprise ServiceNow environments."
    ]
    for b in pyr_bullets:
        story.append(Paragraph(f"&bull; {b}", bullet_style))

    story.append(Paragraph("TECHNICAL PROJECTS & SYSTEMS ENGINEERING", section_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=primary, spaceAfter=4))
    projects = [
        ("Portsy – Distributed File Synchronization & State Engine", "Go, Wails, TypeScript, Firestore",
         "Architected lightweight desktop background synchronization utility in Go utilizing low-level OS file-system event listeners; engineered conflict-resolution algorithms for concurrent writes, file locks, and offline resilience."),
        ("EcoCommerce – Scalable Relational Data Platform & API Service", "Node.js, TypeScript, React, Prisma, SQL",
         "Designed full-stack data platform with strictly typed relational schemas, query optimization, robust REST APIs, DNS management, and uptime monitoring.")
    ]
    for p_name, p_stack, p_desc in projects:
        story.append(Paragraph(f"&bull; <b>{p_name}</b> (<i>{p_stack}</i>): {p_desc}", bullet_style))

    story.append(Paragraph("EDUCATION & CERTIFICATIONS", section_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=primary, spaceAfter=4))
    story.append(Paragraph("<b>Coursework in Computer Science (2 Years Completed)</b> &mdash; Glendale Community College, Glendale, CA", body_style))
    story.append(Paragraph("<b>Certificate in Digital Systems & Audio Engineering</b> &mdash; Icon Collective, Los Angeles, CA", body_style))

    doc.build(story)
    return output_pdf_path
