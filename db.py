"""
db.py - SQLite Database manager for Job Engine.
Manages job storage, status tracking, deduplication, and matching metadata.
"""

import sqlite3
import hashlib
from typing import Dict, List, Optional, Any
from pathlib import Path

DB_FILE = Path(__file__).parent / "jobs.db"

def get_connection(db_path: Path = DB_FILE) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path = DB_FILE) -> None:
    """Initialize SQLite database schema and apply safe migrations."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT,
                salary_range TEXT,
                url TEXT NOT NULL,
                description TEXT,
                date_posted TEXT,
                source TEXT,
                status TEXT DEFAULT 'new', -- 'new', 'matched', 'applied', 'rejected'
                score REAL DEFAULT 0,
                match_reasons TEXT,
                tailored_resume_path TEXT,
                cold_email_path TEXT,
                reported_date TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Safe migration for existing DBs
        try:
            cursor.execute("ALTER TABLE jobs ADD COLUMN reported_date TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_reported_date ON jobs(reported_date)")
        conn.commit()

def generate_job_id(company: str, title: str, url: str) -> str:
    """Generate a stable, unique job ID using company, title, and URL."""
    clean_str = f"{company.strip().lower()}|{title.strip().lower()}|{url.strip().lower()}"
    return hashlib.sha256(clean_str.encode("utf-8")).hexdigest()[:16]

def job_exists(job_id: str, db_path: Path = DB_FILE) -> bool:
    """Check if a job already exists in the database."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,))
        return cursor.fetchone() is not None

def insert_job(job_data: Dict[str, Any], db_path: Path = DB_FILE) -> bool:
    """Insert a job if it doesn't already exist. Returns True if inserted, False if duplicate."""
    job_id = job_data.get("job_id") or generate_job_id(
        job_data.get("company", ""),
        job_data.get("title", ""),
        job_data.get("url", "")
    )
    job_data["job_id"] = job_id

    if job_exists(job_id, db_path):
        new_sal = job_data.get("salary_range", "Not specified")
        if new_sal and new_sal != "Not specified":
            with get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE jobs SET salary_range = ?, description = ?
                    WHERE job_id = ? AND (salary_range = 'Not specified' OR LENGTH(?) > LENGTH(salary_range))
                """, (new_sal, job_data.get("description", ""), job_id, new_sal))
                conn.commit()
        return False

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (
                job_id, company, title, location, salary_range,
                url, description, date_posted, source, status,
                score, match_reasons, tailored_resume_path, cold_email_path,
                reported_date
            ) VALUES (
                :job_id, :company, :title, :location, :salary_range,
                :url, :description, :date_posted, :source, :status,
                :score, :match_reasons, :tailored_resume_path, :cold_email_path,
                :reported_date
            )
        """, {
            "job_id": job_id,
            "company": job_data.get("company", "").strip(),
            "title": job_data.get("title", "").strip(),
            "location": job_data.get("location", "Remote"),
            "salary_range": job_data.get("salary_range", "Not specified"),
            "url": job_data.get("url", "").strip(),
            "description": job_data.get("description", ""),
            "date_posted": job_data.get("date_posted", ""),
            "source": job_data.get("source", "unknown"),
            "status": job_data.get("status", "new"),
            "score": job_data.get("score", 0.0),
            "match_reasons": job_data.get("match_reasons", ""),
            "tailored_resume_path": job_data.get("tailored_resume_path", ""),
            "cold_email_path": job_data.get("cold_email_path", ""),
            "reported_date": job_data.get("reported_date", None)
        })
        conn.commit()
    return True

def get_jobs_by_status(status: str, db_path: Path = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieve jobs matching a given status."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE status = ? ORDER BY score DESC, created_at DESC", (status,))
        return [dict(row) for row in cursor.fetchall()]

def get_all_jobs(db_path: Path = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieve all jobs in the database."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY score DESC, created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

def update_job_match(
    job_id: str,
    score: float,
    status: str,
    match_reasons: str,
    resume_path: Optional[str] = None,
    email_path: Optional[str] = None,
    db_path: Path = DB_FILE
) -> None:
    """Update a job's match score, status, and generated asset paths."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE jobs
            SET score = ?,
                status = ?,
                match_reasons = ?,
                tailored_resume_path = COALESCE(?, tailored_resume_path),
                cold_email_path = COALESCE(?, cold_email_path),
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
        """, (score, status, match_reasons, resume_path, email_path, job_id))
        conn.commit()

def mark_job_reported(job_id: str, reported_date: str, db_path: Path = DB_FILE) -> None:
    """Mark a job with the date it was included in daily_matches.md."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE jobs
            SET reported_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
        """, (reported_date, job_id))
        conn.commit()

def get_unreported_jobs(min_score: float = 60.0, db_path: Path = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieve fresh matched jobs that have not been reported yet."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM jobs
            WHERE (reported_date IS NULL OR reported_date = '')
              AND score >= ?
            ORDER BY score DESC, created_at DESC
        """, (min_score,))
        return [dict(row) for row in cursor.fetchall()]

def get_recently_reported_jobs(days: int = 7, min_score: float = 60.0, db_path: Path = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieve jobs reported in the last N days."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM jobs
            WHERE reported_date IS NOT NULL
              AND reported_date != ''
              AND reported_date >= date('now', '-' || ? || ' days')
              AND score >= ?
            ORDER BY reported_date DESC, score DESC
        """, (days, min_score))
        return [dict(row) for row in cursor.fetchall()]

def get_top_matches(limit: int = 10, min_score: float = 60.0, db_path: Path = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieve top matched jobs with score >= min_score."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM jobs
            WHERE score >= ?
            ORDER BY score DESC, created_at DESC
            LIMIT ?
        """, (min_score, limit))
        return [dict(row) for row in cursor.fetchall()]

if __name__ == "__main__":
    init_db()
    print(f"Database initialized and schema migrated at {DB_FILE}")
