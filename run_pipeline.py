"""
run_pipeline.py - Autonomous Job Engine Master Pipeline Runner.

Orchestrates the complete local pipeline:
1. Sourcing & Aggregation (fetch_jobs.py -> jobs.db)
2. ATS Keyword Extraction, Relevance Scoring, & Asset Generation (match_and_tailor.py)
3. Generates daily_matches.md and displays formatted terminal summary table.
"""

import sys
import time
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from fetch_jobs import aggregate_and_store_jobs
from match_and_tailor import run_match_and_tailor

def main():
    start_time = time.time()
    print("\n" + "#"*80)
    print("AUTONOMOUS JOB SOURCING, MATCHING & ATS TAILORING ENGINE")
    print("Profile: Robert Warren | Target Market: Remote & Dayton / Cincinnati / Columbus, OH")
    print("Filter: 100% Free Local Engine | Zero Security Clearance / Zero Government Roles")
    print("#"*80 + "\n")

    # Step 1: Run Scrapers
    print(">>> STEP 1: Sourcing Commercial Listings into SQLite (jobs.db)...")
    new_jobs = aggregate_and_store_jobs()

    # Step 2: Run Matching & Tailoring
    print(">>> STEP 2: Running ATS Matcher & Generating Tailored Application Assets...")
    top_matches = run_match_and_tailor()

    elapsed = time.time() - start_time
    print(f"[SUCCESS] Complete pipeline finished in {elapsed:.1f}s.")
    print(f"Top matches recorded in daily_matches.md and outputs/ directory.")

if __name__ == "__main__":
    main()
