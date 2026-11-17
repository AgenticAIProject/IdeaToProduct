"""
db_logger.py - SQLite Audit and Session Logger for IdeaToProduct SDLC Pipeline.

Provides persistent storage, governance sign-off audit trails, and execution logs
in a zero-dependency SQLite database (logs/pipeline_audit.db).
"""

import os
import json
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

DB_DIR = Path(__file__).resolve().parent.parent / "logs"
DB_PATH = DB_DIR / "pipeline_audit.db"
_DB_LOCK = threading.Lock()


def _get_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize SQLite database tables and indices."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        project_id TEXT,
                        idea TEXT,
                        stage TEXT,
                        status TEXT,
                        approval_status TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        result_json TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS stage_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        stage TEXT,
                        version INTEGER,
                        status TEXT,
                        summary TEXT,
                        token_usage_json TEXT,
                        created_at TEXT,
                        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS governance_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        event_type TEXT,
                        stage TEXT,
                        verdict TEXT,
                        score REAL,
                        details_json TEXT,
                        created_at TEXT,
                        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_stage_logs_session ON stage_logs(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_governance_session ON governance_audit(session_id)")
        finally:
            conn.close()


def save_session(session_id: str, data: dict[str, Any]) -> None:
    """Save or update a pipeline session in SQLite."""
    now = datetime.now(timezone.utc).isoformat()
    project_id = str(data.get("project_id", ""))
    idea = str(data.get("idea", ""))
    stage = str(data.get("stage", "requirements"))
    status = str(data.get("status", "running"))
    approval_status = str(data.get("result", {}).get("approval_status") or data.get("approval_status", "pending"))
    result_json = json.dumps(data.get("result", {}), default=str)

    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO sessions (session_id, project_id, idea, stage, status, approval_status, created_at, updated_at, result_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        stage = excluded.stage,
                        status = excluded.status,
                        approval_status = excluded.approval_status,
                        updated_at = excluded.updated_at,
                        result_json = excluded.result_json
                """, (session_id, project_id, idea, stage, status, approval_status, now, now, result_json))
        finally:
            conn.close()


def get_session(session_id: str) -> Optional[dict[str, Any]]:
    """Retrieve a session from SQLite by session_id."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["result"] = json.loads(res.get("result_json") or "{}")
            except Exception:
                res["result"] = {}
            return res
        finally:
            conn.close()


def load_all_sessions() -> dict[str, dict[str, Any]]:
    """Load all sessions into memory dictionary for fast server startup."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions ORDER BY created_at DESC")
            rows = cursor.fetchall()
            loaded = {}
            for row in rows:
                item = dict(row)
                try:
                    item["result"] = json.loads(item.get("result_json") or "{}")
                except Exception:
                    item["result"] = {}
                item["is_running"] = False
                loaded[item["session_id"]] = item
            return loaded
        finally:
            conn.close()


def log_stage_execution(
    session_id: str,
    stage: str,
    version: int,
    status: str,
    summary: str = "",
    token_usage: Optional[dict] = None
) -> None:
    """Log an immutable record of a completed agent stage to the SQLite audit log."""
    now = datetime.now(timezone.utc).isoformat()
    usage_json = json.dumps(token_usage or {}, default=str)
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO stage_logs (session_id, stage, version, status, summary, token_usage_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (session_id, stage, version, status, summary, usage_json, now))
        finally:
            conn.close()


def log_governance_signoff(
    session_id: str,
    stage: str,
    verdict: str,
    score: float,
    details: Optional[dict] = None
) -> None:
    """Log Quality Gate governance sign-off (required before Release node)."""
    now = datetime.now(timezone.utc).isoformat()
    details_json = json.dumps(details or {}, default=str)
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO governance_audit (session_id, event_type, stage, verdict, score, details_json, created_at)
                    VALUES (?, 'quality_gate_signoff', ?, ?, ?, ?, ?)
                """, (session_id, stage, verdict, score, details_json, now))
        finally:
            conn.close()


# Auto-initialize database on import
init_db()
