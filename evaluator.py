"""
evaluator.py - Retrieval-Augmented Job Evaluation Layer using Gemini API.

Evaluates raw job descriptions with structured JSON output enforcing the JobEvaluation schema:
- Screens for hands-on technical vs coordination/delegation roles.
- Flags people management duties.
- Extracts core tech stack.
- Determines actual remote status (Fully Remote, Hybrid, Onsite).
- Scores red flags and corporate jargon.
- Produces a ruthless 1-sentence executive summary.
- Computes pass/fail based on remote work and zero management requirement.
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

# Ensure environment variables from .env in project root are loaded
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

from google import genai
from google.genai import types
from google.genai.errors import ClientError, APIError

logger = logging.getLogger(__name__)

# Model configuration:
# gemini-2.5-flash is designated for high-speed, low-cost processing.
# gemini-3.8-flash serves as drop-in fallback if gemini-2.5-flash is unavailable or deprecated.
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL = "gemini-3.8-flash"
ACTIVE_MODEL: Optional[str] = None


class JobEvaluation(BaseModel):
    """
    Structured evaluation schema for assessing scraped job postings.
    """
    is_hands_on_technical: bool = Field(
        description="Whether the role involves direct hands-on technical execution (coding, engineering, debugging, systems administration) rather than pure management, coordination, or administrative theater."
    )
    requires_people_management: bool = Field(
        description="Whether the role requires managing people (direct reports, performance reviews, hiring/firing)."
    )
    core_tech_stack: List[str] = Field(
        default_factory=list,
        description="List of primary technologies, programming languages, frameworks, databases, or systems explicitly required."
    )
    actual_remote_status: Literal["Fully Remote", "Hybrid", "Onsite"] = Field(
        description="Must be 'Fully Remote', 'Hybrid', or 'Onsite'. Flag bait-and-switch where the posting claims remote but text specifies mandatory in-office attendance."
    )
    red_flag_score: int = Field(
        ge=0,
        le=10,
        description="Integer score from 0 (clean, direct) to 10 (severe red flags: corporate jargon soup, toxic culture, bait-and-switch, 24/7 on-call abuse, vague responsibilities)."
    )
    bullshit_jargon_ratio: Literal["Low", "Medium", "High"] = Field(
        description="Must be 'Low', 'Medium', or 'High' reflecting the density of corporate filler and empty buzzwords."
    )
    executive_summary: str = Field(
        description="Exactly 1 sentence summarizing the actual day-to-day deliverables and core responsibilities, ruthlessly stripping all corporate filler."
    )
    pass_fail: bool = Field(
        description="True if remote (Fully Remote) and no management required (requires_people_management is False), False otherwise."
    )

    @model_validator(mode="after")
    def validate_pass_fail(self) -> "JobEvaluation":
        """Enforces pass_fail rule: True if remote and no management required, False otherwise."""
        is_remote = self.actual_remote_status == "Fully Remote"
        no_mgmt = not self.requires_people_management
        self.pass_fail = bool(is_remote and no_mgmt)
        return self


SYSTEM_INSTRUCTION = (
    "You are a ruthless, highly technical technical screener filtering out roles that "
    "require people management, heavy corporate theater, or onsite attendance. "
    "Your evaluation must be objective, critical, and strictly grounded in the text. "
    "Filter out corporate jargon and highlight the actual ground reality of the day-to-day role."
)

PROMPT_TEMPLATE = """Evaluate the following job posting thoroughly.

Criteria:
1. is_hands_on_technical: True if the role requires hands-on technical work (code, diagnostics, infrastructure, low-level support), False if mostly meetings, coordination, or slide decks.
2. requires_people_management: True if the role involves direct reports, performance reviews, or hiring/firing.
3. core_tech_stack: Array of specific technologies, languages, tools, frameworks mentioned (e.g. ['Python', 'SQL', 'Docker']).
4. actual_remote_status: Must be 'Fully Remote', 'Hybrid', or 'Onsite'. Scrutinize the text for any hidden in-office or hybrid requirements.
5. red_flag_score: 0-10 integer score. High scores for buzzwords, vague duties, on-call abuse, 'fast-paced environment / wear many hats'.
6. bullshit_jargon_ratio: 'Low', 'Medium', or 'High'.
7. executive_summary: Exactly 1 concise sentence stating what the hire actually builds or fixes. No fluff.
8. pass_fail: True if remote and no people management required, False otherwise.

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

    Uses the gemini-2.5-flash model (with fallback to gemini-3.8-flash if deprecated/unavailable),
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
                import json
                parsed_data = json.loads(response.text)
                eval_obj = JobEvaluation.model_validate(parsed_data)
                ACTIVE_MODEL = target_model
                return eval_obj

            raise ValueError("Gemini API returned an empty response.")

        except ClientError as ce:
            last_error = ce
            err_msg = str(ce)
            # Handle model availability/deprecation (e.g. gemini-2.5-flash 404 falling back to gemini-3.8-flash)
            if ("404" in err_msg or "not available" in err_msg.lower() or "not_found" in err_msg.lower()) and target_model != FALLBACK_MODEL:
                print(f"[!] Notice: Model '{target_model}' is unavailable/deprecated. Switching to '{FALLBACK_MODEL}'.")
                target_model = FALLBACK_MODEL
                ACTIVE_MODEL = FALLBACK_MODEL
                continue

            # Exponential backoff for rate limits (429) or transient client errors
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
    Senior Python Backend Engineer (100% Remote - US)
    Acme Software Inc.
    
    We are seeking a Senior Python Engineer to design, build, and maintain high-throughput REST APIs
    and data processing microservices. You will work with FastAPI, PostgreSQL, Redis, and AWS ECS.
    
    Responsibilities:
    - Write clean, test-driven Python code for backend microservices.
    - Optimize database queries and handle asynchronous queue workers with Celery.
    - Troubleshoot production issues and participate in code reviews.
    
    Requirements:
    - 5+ years of experience with Python, SQL, and distributed systems.
    - Strong understanding of Docker, CI/CD, and Linux environments.
    - No direct reports. Pure hands-on technical execution.
    - 100% remote within the United States.
    """
    print("Testing evaluate_job_description with sample posting...")
    evaluation = evaluate_job_description(sample_desc)
    print("\n--- Evaluation Result ---")
    print(evaluation.model_dump_json(indent=2))
