"""
resume_exporter.py - Professional ATS Resume Exporter for Job Engine.
Exports tailored resumes into:
1. Microsoft Word Document (.docx) - 100% ATS compliant, styled typography.
2. Adobe PDF Document (.pdf) - Executive print-ready layout via Playwright.
3. Markdown (.md) - Plaintext reference and documentation.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

from playwright.sync_api import sync_playwright

NAVY = RGBColor(16, 44, 87)       # Primary header color
CHARCOAL = RGBColor(34, 34, 34)   # Body text color
MUTED = RGBColor(90, 90, 90)      # Subtitle/meta color

def add_bottom_border(paragraph):
    """Add a sleek, professional bottom border under section headers in Word."""
    pPr = paragraph._element.get_or_add_pPr()
    pBdr = parse_xml(r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                     r'<w:bottom w:val="single" w:sz="6" w:space="2" w:color="102C57"/>'
                     r'</w:pBdr>')
    pPr.append(pBdr)

def export_resume_docx(
    company: str,
    title: str,
    summary: str,
    competencies: List[Tuple[str, str]],
    midmark_bullets: List[str],
    output_docx_path: Path
) -> Path:
    """Generate an ATS-friendly, executive-formatted Microsoft Word (.docx) resume."""
    doc = docx.Document()

    # 0.6 inch margins
    for section in doc.sections:
        section.top_margin = Inches(0.55)
        section.bottom_margin = Inches(0.55)
        section.left_margin = Inches(0.6)
        section.right_margin = Inches(0.6)

    # 1. Header: Candidate Name
    p_name = doc.add_paragraph()
    p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_name.paragraph_format.space_before = Pt(0)
    p_name.paragraph_format.space_after = Pt(2)
    run_name = p_name.add_run("Robert Warren")
    run_name.font.name = "Calibri"
    run_name.font.size = Pt(22)
    run_name.font.bold = True
    run_name.font.color.rgb = NAVY

    # Contact Info
    p_contact = doc.add_paragraph()
    p_contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_contact.paragraph_format.space_before = Pt(0)
    p_contact.paragraph_format.space_after = Pt(2)
    run_contact = p_contact.add_run("Dayton, OH  •  (626) 872-4171  •  robertcwarren1@gmail.com  •  linkedin.com/in/robert-c-warren")
    run_contact.font.name = "Calibri"
    run_contact.font.size = Pt(10)
    run_contact.font.color.rgb = MUTED

    # Target Subtitle
    p_target = doc.add_paragraph()
    p_target.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_target.paragraph_format.space_before = Pt(0)
    p_target.paragraph_format.space_after = Pt(10)
    run_target = p_target.add_run(f"Target Role: {title}  |  {company}")
    run_target.font.name = "Calibri"
    run_target.font.size = Pt(10.5)
    run_target.font.bold = True
    run_target.font.color.rgb = NAVY

    def add_section_heading(text: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text.upper())
        run.font.name = "Calibri"
        run.font.size = Pt(11.5)
        run.font.bold = True
        run.font.color.rgb = NAVY
        add_bottom_border(p)
        return p

    # 2. Professional Summary
    add_section_heading("Professional Summary")
    p_sum = doc.add_paragraph()
    p_sum.paragraph_format.space_before = Pt(2)
    p_sum.paragraph_format.space_after = Pt(6)
    p_sum.paragraph_format.line_spacing = 1.15
    run_sum = p_sum.add_run(summary)
    run_sum.font.name = "Calibri"
    run_sum.font.size = Pt(10)
    run_sum.font.color.rgb = CHARCOAL

    # 3. Core Competencies
    add_section_heading("Core Competencies & Technical Skills")
    for cat_name, cat_desc in competencies:
        p_c = doc.add_paragraph(style='List Bullet')
        p_c.paragraph_format.space_before = Pt(1)
        p_c.paragraph_format.space_after = Pt(2)
        p_c.paragraph_format.line_spacing = 1.12
        r_bold = p_c.add_run(f"{cat_name}: ")
        r_bold.font.name = "Calibri"
        r_bold.font.size = Pt(9.5)
        r_bold.font.bold = True
        r_bold.font.color.rgb = CHARCOAL

        r_text = p_c.add_run(cat_desc)
        r_text.font.name = "Calibri"
        r_text.font.size = Pt(9.5)
        r_text.font.color.rgb = CHARCOAL

    # 4. Professional Experience
    add_section_heading("Professional Experience")

    # Midmark
    p_job1 = doc.add_paragraph()
    p_job1.paragraph_format.space_before = Pt(5)
    p_job1.paragraph_format.space_after = Pt(1)
    p_job1.paragraph_format.keep_with_next = True
    r1 = p_job1.add_run("Midmark Corporation")
    r1.font.bold = True
    r1.font.size = Pt(10.5)
    r1.font.color.rgb = NAVY
    r1_sub = p_job1.add_run("  |  Versailles, OH  —  Associate Technical Service Specialist  (Jun 2024 – Sep 2026)")
    r1_sub.font.italic = True
    r1_sub.font.size = Pt(10)
    r1_sub.font.color.rgb = MUTED

    for b in midmark_bullets:
        p_b = doc.add_paragraph(style='List Bullet')
        p_b.paragraph_format.space_before = Pt(1)
        p_b.paragraph_format.space_after = Pt(2)
        p_b.paragraph_format.line_spacing = 1.12
        # Bold lead-in if there's a colon
        if ":" in b and len(b.split(":")[0]) < 45:
            prefix, rest = b.split(":", 1)
            rb = p_b.add_run(prefix + ":")
            rb.font.bold = True
            rb.font.size = Pt(9.5)
            rt = p_b.add_run(rest)
            rt.font.size = Pt(9.5)
        else:
            rt = p_b.add_run(b)
            rt.font.size = Pt(9.5)
        p_b.runs[0].font.name = "Calibri"

    # Quality Boat Salvage
    p_job2 = doc.add_paragraph()
    p_job2.paragraph_format.space_before = Pt(5)
    p_job2.paragraph_format.space_after = Pt(1)
    p_job2.paragraph_format.keep_with_next = True
    r2 = p_job2.add_run("Quality Boat Salvage")
    r2.font.bold = True
    r2.font.size = Pt(10.5)
    r2.font.color.rgb = NAVY
    r2_sub = p_job2.add_run("  |  Pasadena, CA  —  Data & Operations Systems Specialist  (Mar 2023 – Jun 2024)")
    r2_sub.font.italic = True
    r2_sub.font.size = Pt(10)
    r2_sub.font.color.rgb = MUTED

    qbs_bullets = [
        "Architected automated inventory synchronization pipelines and data-handling scripts in Python, reducing sync cycle times by 20% while eliminating state desynchronization.",
        "Administered cloud directory accounts, access controls, multi-factor authentication (MFA), and data integrity standards across operational tools and databases.",
        "Authored operational runbooks, hardware maintenance guides, and system troubleshooting SOPs to standardize staff onboarding and technical procedures."
    ]
    for b in qbs_bullets:
        p_b = doc.add_paragraph(style='List Bullet')
        p_b.paragraph_format.space_before = Pt(1)
        p_b.paragraph_format.space_after = Pt(2)
        p_b.paragraph_format.line_spacing = 1.12
        rt = p_b.add_run(b)
        rt.font.name = "Calibri"
        rt.font.size = Pt(9.5)

    # Pyramid Consulting
    p_job3 = doc.add_paragraph()
    p_job3.paragraph_format.space_before = Pt(5)
    p_job3.paragraph_format.space_after = Pt(1)
    p_job3.paragraph_format.keep_with_next = True
    r3 = p_job3.add_run("Pyramid Consulting, Inc.")
    r3.font.bold = True
    r3.font.size = Pt(10.5)
    r3.font.color.rgb = NAVY
    r3_sub = p_job3.add_run("  |  Remote / Los Angeles, CA  —  IT Systems Engineer (Contract)  (May 2022 – Nov 2022)")
    r3_sub.font.italic = True
    r3_sub.font.size = Pt(10)
    r3_sub.font.color.rgb = MUTED

    pyr_bullets = [
        "Delivered enterprise L2/L3 systems support for distributed Windows and macOS endpoints, corporate VPNs, and AWS identity/access configurations.",
        "Triaged web application performance degradation, REST API failures, and runtime defects utilizing browser developer tools, HTTP request inspection, and server-side log output.",
        "Maintained a 95%+ first-contact satisfaction rating handling escalated technical tickets within enterprise ServiceNow environments."
    ]
    for b in pyr_bullets:
        p_b = doc.add_paragraph(style='List Bullet')
        p_b.paragraph_format.space_before = Pt(1)
        p_b.paragraph_format.space_after = Pt(2)
        p_b.paragraph_format.line_spacing = 1.12
        rt = p_b.add_run(b)
        rt.font.name = "Calibri"
        rt.font.size = Pt(9.5)

    # 5. Technical Projects
    add_section_heading("Technical Projects & Systems Engineering")
    projects = [
        ("Portsy – Distributed File Synchronization Engine (Go, Wails, TypeScript, Firestore)",
         "Built lightweight desktop background synchronization utility in Go utilizing low-level OS file-system event listeners; engineered conflict-resolution algorithms for concurrent writes, file locks, and offline resilience."),
        ("EcoCommerce – Scalable Relational Data Platform (Node.js, TypeScript, React, Prisma, SQL)",
         "Designed full-stack platform with strictly typed relational schemas, query optimization, robust REST APIs, DNS management, and uptime monitoring.")
    ]
    for p_title, p_desc in projects:
        p_pr = doc.add_paragraph(style='List Bullet')
        p_pr.paragraph_format.space_before = Pt(1)
        p_pr.paragraph_format.space_after = Pt(2)
        p_pr.paragraph_format.line_spacing = 1.12
        rb = p_pr.add_run(p_title + ": ")
        rb.font.bold = True
        rb.font.size = Pt(9.5)
        rt = p_pr.add_run(p_desc)
        rt.font.size = Pt(9.5)
        p_pr.runs[0].font.name = "Calibri"

    # 6. Education
    add_section_heading("Education & Credentials")
    p_edu = doc.add_paragraph()
    p_edu.paragraph_format.space_before = Pt(2)
    p_edu.paragraph_format.space_after = Pt(2)
    r_edu1 = p_edu.add_run("Associate of Science (AS), Computer Science")
    r_edu1.font.bold = True
    r_edu1.font.size = Pt(9.5)
    r_edu1_sub = p_edu.add_run("  —  Glendale Community College, Glendale, CA\n")
    r_edu1_sub.font.size = Pt(9.5)
    r_edu2 = p_edu.add_run("Certificate in Digital Systems & Audio Engineering")
    r_edu2.font.bold = True
    r_edu2.font.size = Pt(9.5)
    r_edu2_sub = p_edu.add_run("  —  Icon Collective, Los Angeles, CA")
    r_edu2_sub.font.size = Pt(9.5)
    p_edu.runs[0].font.name = "Calibri"

    doc.save(output_docx_path)
    return output_docx_path

def export_resume_pdf(
    company: str,
    title: str,
    summary: str,
    competencies: List[Tuple[str, str]],
    midmark_bullets: List[str],
    output_pdf_path: Path
) -> Path:
    """Generate a pixel-perfect, modern PDF resume using Playwright Chromium."""

    # Build HTML representation
    comp_html = "".join([f"<li><strong>{cat_name}:</strong> {cat_desc}</li>" for cat_name, cat_desc in competencies])
    
    midmark_html = []
    for b in midmark_bullets:
        if ":" in b and len(b.split(":")[0]) < 45:
            pfx, rest = b.split(":", 1)
            midmark_html.append(f"<li><strong>{pfx}:</strong>{rest}</li>")
        else:
            midmark_html.append(f"<li>{b}</li>")
    midmark_str = "".join(midmark_html)

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: letter;
    margin: 0.5in 0.55in;
  }}
  * {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #222222;
    line-height: 1.35;
    font-size: 9.5pt;
    margin: 0;
    padding: 0;
  }}
  .header {{
    text-align: center;
    margin-bottom: 8px;
  }}
  .name {{
    font-size: 20pt;
    font-weight: 700;
    color: #102C57;
    margin: 0 0 2px 0;
    letter-spacing: -0.2px;
  }}
  .contact {{
    font-size: 9pt;
    color: #555555;
    margin-bottom: 3px;
  }}
  .contact a {{
    color: #102C57;
    text-decoration: none;
  }}
  .target-badge {{
    font-size: 9.5pt;
    font-weight: 600;
    color: #102C57;
    background: #EEF4FB;
    display: inline-block;
    padding: 2px 10px;
    border-radius: 4px;
    margin-top: 2px;
  }}
  h2 {{
    font-size: 10.5pt;
    text-transform: uppercase;
    color: #102C57;
    border-bottom: 1px solid #102C57;
    padding-bottom: 2px;
    margin: 9px 0 4px 0;
    letter-spacing: 0.5px;
  }}
  p {{
    margin: 0 0 4px 0;
  }}
  .summary {{
    text-align: justify;
    line-height: 1.35;
    color: #333333;
  }}
  ul {{
    margin: 0 0 5px 0;
    padding-left: 17px;
  }}
  li {{
    margin-bottom: 2.5px;
    line-height: 1.32;
  }}
  .job-title-row {{
    display: flex;
    justify-content: space-between;
    margin-top: 4px;
    margin-bottom: 2px;
  }}
  .company {{
    font-weight: 700;
    color: #102C57;
    font-size: 10pt;
  }}
  .role-title {{
    font-style: italic;
    color: #444444;
  }}
  .date-loc {{
    font-size: 9pt;
    color: #666666;
    text-align: right;
  }}
  .edu-row {{
    margin-bottom: 3px;
  }}
</style>
</head>
<body>
  <div class="header">
    <div class="name">Robert Warren</div>
    <div class="contact">
      Dayton, OH &bull; (626) 872-4171 &bull; <a href="mailto:robertcwarren1@gmail.com">robertcwarren1@gmail.com</a> &bull; <a href="https://linkedin.com/in/robert-c-warren">linkedin.com/in/robert-c-warren</a>
    </div>
    <div class="target-badge">Target Role: {title} &bull; {company}</div>
  </div>

  <h2>Professional Summary</h2>
  <div class="summary">{summary}</div>

  <h2>Core Competencies & Technical Skills</h2>
  <ul>
    {comp_html}
  </ul>

  <h2>Professional Experience</h2>
  <div class="job-title-row">
    <div><span class="company">Midmark Corporation</span> <span class="role-title">&mdash; Associate Technical Service Specialist</span></div>
    <div class="date-loc">Versailles, OH | Jun 2024 &ndash; Sep 2026</div>
  </div>
  <ul>
    {midmark_str}
  </ul>

  <div class="job-title-row">
    <div><span class="company">Quality Boat Salvage</span> <span class="role-title">&mdash; Data & Operations Systems Specialist</span></div>
    <div class="date-loc">Pasadena, CA | Mar 2023 &ndash; Jun 2024</div>
  </div>
  <ul>
    <li>Architected automated inventory synchronization pipelines and data-handling scripts in Python, reducing sync cycle times by 20% while eliminating state desynchronization.</li>
    <li>Administered cloud directory accounts, access controls, multi-factor authentication (MFA), and data integrity standards across operational tools and databases.</li>
    <li>Authored operational runbooks, hardware maintenance guides, and system troubleshooting SOPs to standardize staff onboarding and technical procedures.</li>
  </ul>

  <div class="job-title-row">
    <div><span class="company">Pyramid Consulting, Inc.</span> <span class="role-title">&mdash; IT Systems Engineer (Contract)</span></div>
    <div class="date-loc">Remote / Los Angeles, CA | May 2022 &ndash; Nov 2022</div>
  </div>
  <ul>
    <li>Delivered enterprise L2/L3 systems support for distributed Windows and macOS endpoints, corporate VPNs, and AWS identity/access configurations.</li>
    <li>Triaged web application performance degradation, REST API failures, and runtime defects utilizing browser developer tools, HTTP request inspection, and server-side log output.</li>
    <li>Maintained a 95%+ first-contact satisfaction rating handling escalated technical tickets within enterprise ServiceNow environments.</li>
  </ul>

  <h2>Technical Projects & Systems Engineering</h2>
  <ul>
    <li><strong>Portsy – Distributed File Synchronization Engine (Go, Wails, TypeScript, Firestore):</strong> Built lightweight desktop background synchronization utility in Go utilizing OS file-system event listeners; engineered conflict-resolution algorithms for concurrent writes, file locks, and offline resilience.</li>
    <li><strong>EcoCommerce – Scalable Relational Data Platform (Node.js, TypeScript, React, Prisma, SQL):</strong> Designed full-stack platform with strictly typed relational schemas, query optimization, robust REST APIs, DNS management, and uptime monitoring.</li>
  </ul>

  <h2>Education & Credentials</h2>
  <div class="edu-row"><strong>Associate of Science (AS), Computer Science</strong> &mdash; Glendale Community College, Glendale, CA</div>
  <div class="edu-row"><strong>Certificate in Digital Systems & Audio Engineering</strong> &mdash; Icon Collective, Los Angeles, CA</div>
</body>
</html>"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_doc)
        page.pdf(
            path=str(output_pdf_path),
            format="Letter",
            margin={"top": "0.45in", "bottom": "0.45in", "left": "0.5in", "right": "0.5in"},
            print_background=True
        )
        browser.close()
    return output_pdf_path
