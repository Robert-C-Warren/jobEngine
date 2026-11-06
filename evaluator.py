"""
evaluator.py - Retrieval-Augmented Job Evaluation Layer using Gemini API.

Evaluates raw job descriptions with structured JSON output enforcing the JobEvaluation schema:
- Scores roles from 0 to 100 as B2B SaaS Technical Support, Integration, or Product Analyst
  bridge roles toward Solutions Engineering.
- Evaluates 5 REQUIRED DNA pillars (+20 points each).
- Applies TRAP JOB PENALTIES (-50 points each; immediate 0/rejection if 2 or more are found).
- Returns {"score": int, "reasoning": str, "trap_flags": list, "tool_blockers": list}.
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

# Ensure environment variables from .env in project root are loaded
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

from google import genai
from google.genai import types
from google.genai.errors import ClientError

logger = logging.getLogger(__name__)

# Model configuration:
# gemini-2.5-flash is designated for high-speed, low-cost processing.
# gemini-3.8-flash serves as drop-in fallback if gemini-2.5-flash is unavailable or deprecated.
_env_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
DEFAULT_MODEL = "gemini-3.8-flash" if _env_model == "gemini-2.5-flash" else _env_model
FALLBACK_MODEL = "gemini-3.8-flash"
ACTIVE_MODEL: Optional[str] = None


class JobEvaluation(BaseModel):
    """
    Structured evaluation schema for scoring B2B SaaS Technical Support, Integration,
    and Product Analyst bridge roles toward Solutions Engineering.
    """
    score: int = Field(
        ge=0,
        le=100,
        description="Overall score from 0 to 100 based on REQUIRED DNA (+20 points each) and TRAP JOB PENALTIES (-50 points each; 0 if two or more traps are found)."
    )
    reasoning: str = Field(
        description="Brief explanation breaking down the DNA points awarded and any trap penalties applied."
    )
    trap_flags: List[str] = Field(
        default_factory=list,
        description="List of any trap keywords or trap categories found in the job description."
    )
    tool_blockers: List[str] = Field(
        default_factory=list,
        description="List of specific software tools, proprietary platforms, or niche certifications required (e.g., Jira, Salesforce, Epic, Workday)."
    )

    @model_validator(mode="after")
    def enforce_trap_rejection(self) -> "JobEvaluation":
        """Reject immediately (score = 0) if two or more trap flags are found, and clamp score to 0-100."""
        if len(self.trap_flags) >= 2:
            self.score = 0
        else:
            self.score = max(0, min(100, int(self.score)))
        return self


SYSTEM_INSTRUCTION = (
    "You are an expert technical recruiter evaluating job descriptions. "
    "Your objective is to find B2B SaaS Technical Support, Integration, or Product Analyst roles "
    "that serve as a bridge to Solutions Engineering."
)

PROMPT_TEMPLATE = """You are an expert technical recruiter evaluating job descriptions. Your objective is to find B2B SaaS Technical Support, Integration, or Product Analyst roles that serve as a bridge to Solutions Engineering.

Evaluate the provided job description and SCORE it from 0 to 100 based on the following criteria:

REQUIRED DNA (+20 points each):
1. B2B SaaS Environment: Must support a software platform or enterprise product.
2. Root-Cause Analysis: Explicit mention of investigating complex bugs, reading logs (e.g., application logs, Windows Event Viewer, CBS logs, Procmon, stack traces), or reproducing issues.
3. Database Interaction: Requires SQL, SQL logs, database querying, or data integrity troubleshooting.
4. Engineering Escalation: Mentions working directly with QA, developers, or product teams to resolve tier 2/tier 3 issues.
5. Technical Stack: Mentions APIs, JSON, webhooks, cloud infrastructure, or deep OS/application/client-server software diagnostics.

TRAP JOB PENALTIES (-50 points each. Reject immediately with score 0 if two or more are found):
- Tier 1 IT Helpdesk or internal corporate IT support.
- Hardware troubleshooting, printer repair, or desktop provisioning.
- Active Directory administration or basic Office 365 password resets.
- High-volume inbound call center metrics.
- Pure backend/ML Software Engineering, pure DevOps/SRE infrastructure architecture, or senior quota-carrying Pre-Sales Solutions Engineering requiring 5+ years of prior sales quota experience.

Output a JSON object with:
{{"score": [number], "reasoning": "[brief explanation]", "trap_flags": [list of any trap keywords found], "tool_blockers": [list of specific software tools required, e.g., Jira, Salesforce]}}

Job Description:
{raw_text}
"""


def get_genai_client() -> genai.Client:
    """Initialize and return the Google GenAI client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Please ensure it is present in .env or the system environment."
        )
    return genai.Client(api_key=api_key)


def evaluate_job_description(
    raw_text: str,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0
) -> JobEvaluation:
    """
    Evaluates a raw job description string and returns a structured JobEvaluation object.

    Uses the configured Gemini model (with fallback to gemini-3.8-flash if deprecated/unavailable),
    enforces structured output schema via types.GenerateContentConfig.response_schema,
    and applies exponential backoff for rate limits or transient errors.
    """
    global ACTIVE_MODEL

    if not raw_text or not raw_text.strip():
        raise ValueError("Cannot evaluate an empty or whitespace-only job description.")

    client = get_genai_client()
    target_model = ACTIVE_MODEL or DEFAULT_MODEL
    delay = initial_delay
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=JobEvaluation,
                system_instruction=SYSTEM_INSTRUCTION
            )

            prompt = PROMPT_TEMPLATE.format(raw_text=raw_text.strip())

            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config
            )

            # Extract parsed structured object
            if response.parsed is not None:
                ACTIVE_MODEL = target_model
                return response.parsed

            # Fallback parsing in case response.text is populated but parsed is not
            if response.text:
                parsed_data = json.loads(response.text)
                eval_obj = JobEvaluation.model_validate(parsed_data)
                ACTIVE_MODEL = target_model
                return eval_obj

            raise ValueError("Gemini API returned an empty response.")

        except ClientError as ce:
            last_error = ce
            err_msg = str(ce)
            if ("404" in err_msg or "not available" in err_msg.lower() or "not_found" in err_msg.lower()) and target_model != FALLBACK_MODEL:
                print(f"[!] Notice: Model '{target_model}' is unavailable/deprecated. Switching to '{FALLBACK_MODEL}'.")
                target_model = FALLBACK_MODEL
                ACTIVE_MODEL = FALLBACK_MODEL
                continue

            if attempt < max_retries:
                print(f"[!] ClientError on attempt {attempt}/{max_retries}: {ce}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(f"All {max_retries} attempts failed due to ClientError: {ce}")
                raise

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                print(f"[!] Error on attempt {attempt}/{max_retries} during job evaluation: {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(f"All {max_retries} attempts failed: {e}")
                raise

    if last_error:
        raise last_error
    raise RuntimeError("evaluate_job_description failed unexpectedly without a captured exception.")


if __name__ == "__main__":
    sample_desc = """
    Tier 3 Application Support Engineer (100% Remote - US)
    Acme SaaS Platform Inc.
    
    We are seeking an Application Support Engineer to investigate complex customer escalations
    for our B2B SaaS platform. You will reproduce software defects, inspect application and SQL logs,
    validate REST API payloads and webhooks, and partner directly with Engineering and QA on Tier 3 bugs.
    
    Responsibilities:
    - Perform deep root-cause analysis (RCA) using system logs, SQL queries, and diagnostic traces.
    - Troubleshoot data integrity issues across relational databases and API integrations.
    - Escalate reproducible defects with full diagnostic logs to software engineering teams.
    
    Requirements:
    - 2+ years in B2B SaaS Technical Support, Application Support, or Integration Support.
    - Strong SQL querying and log analysis skills (Event Viewer, Procmon, or server logs).
    - Experience with REST APIs, JSON, Postman, and Jira.
    """
    print("Testing evaluate_job_description with sample posting...")
    evaluation = evaluate_job_description(sample_desc)
    print("\n--- Evaluation Result ---")
    print(evaluation.model_dump_json(indent=2))
