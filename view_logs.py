"""
IdeaToProduct - Pipeline Audit & Log Viewer
Usage:
    python view_logs.py             # Show all recent sessions summary
    python view_logs.py --last      # Show detailed breakdown of the latest session
    python view_logs.py <session_id> # Show detailed breakdown of a specific session
"""

import sqlite3
import json
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "logs" / "pipeline_audit.db"


def get_connection():
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)
    return sqlite3.connect(str(DB_PATH))


def list_sessions(limit=10):
    conn = get_connection()
    c = conn.cursor()
    rows = c.execute("""
        SELECT session_id, project_id, stage, status, approval_status, created_at, idea 
        FROM sessions 
        ORDER BY rowid DESC 
        LIMIT ?
    """, (limit,)).fetchall()
    
    print("\n" + "=" * 95)
    print(f"  {'SESSION ID':<38} {'PROJECT':<12} {'STAGE':<14} {'STATUS':<8} {'APPROVAL':<10} {'DATE'}")
    print("=" * 95)
    
    for r in rows:
        sid, pid, stage, status, approval, created, idea = r
        date_str = (created or "")[:19].replace("T", " ")
        approval_str = approval or "pending"
        print(f"  {sid:<38} {pid:<12} {stage:<14} {status:<8} {approval_str:<10} {date_str}")
        if idea:
            snippet = idea.strip().replace("\n", " ")
            if len(snippet) > 85:
                snippet = snippet[:82] + "..."
            print(f"    └─ Idea: \"{snippet}\"")
    print("=" * 95 + "\n")
    print("Tip: Run 'python view_logs.py --last' to see full stage details for the latest run.\n")


def view_session_details(session_id: str):
    conn = get_connection()
    c = conn.cursor()
    
    # Session metadata
    sess = c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not sess:
        # Try prefix match
        sess = c.execute("SELECT * FROM sessions WHERE session_id LIKE ? ORDER BY rowid DESC LIMIT 1", (f"{session_id}%",)).fetchone()
        if not sess:
            print(f"Error: Session '{session_id}' not found.")
            return

    col_names = [d[0] for d in c.description]
    sess_dict = dict(zip(col_names, sess))
    actual_sid = sess_dict["session_id"]
    
    print("\n" + "=" * 80)
    print(f"  SESSION DETAILS: {actual_sid}")
    print("=" * 80)
    print(f"  Project ID:      {sess_dict.get('project_id')}")
    print(f"  Final Stage:     {sess_dict.get('stage')}")
    print(f"  Status:          {sess_dict.get('status')}")
    print(f"  Approval:        {sess_dict.get('approval_status')}")
    print(f"  Started:         {sess_dict.get('created_at')}")
    print(f"  Updated:         {sess_dict.get('updated_at')}")
    print(f"  Idea:            {sess_dict.get('idea')}")
    
    # Stage progression
    print("\n" + "-" * 80)
    print("  STAGE PROGRESSION & TOKEN USAGE")
    print("-" * 80)
    stage_rows = c.execute("""
        SELECT stage, version, status, summary, token_usage_json, created_at 
        FROM stage_logs 
        WHERE session_id = ? 
        ORDER BY id ASC
    """, (actual_sid,)).fetchall()
    
    if not stage_rows:
        print("  No stage logs found for this session.")
    else:
        print(f"  {'STAGE':<15} {'VER':<5} {'STATUS':<8} {'MODEL':<24} {'CALLS':<6} {'TOTAL TOKENS':<12} {'TIME'}")
        print("  " + "-" * 76)
        for row in stage_rows:
            stg, ver, stat, summ, tok_json, created = row
            time_part = (created or "")[11:19]
            tok = {}
            if tok_json:
                try:
                    tok = json.loads(tok_json)
                except Exception:
                    pass
            model = tok.get("model", "-")
            calls = tok.get("calls", "-")
            total = tok.get("total_tokens", "-")
            print(f"  {stg:<15} v{ver:<4} {stat:<8} {model:<24} {str(calls):<6} {str(total):<12} {time_part}")
    
    # Check test results and review notes from result_json
    result_raw = sess_dict.get("result_json")
    if result_raw:
        try:
            res = json.loads(result_raw)
            print("\n" + "-" * 80)
            print("  QUALITY GATE & TEST OUTCOME")
            print("-" * 80)
            
            # Tests
            test_res = res.get("test_results") or {}
            print(f"  Tests Passed:   {test_res.get('all_passed')}")
            print(f"  Test Summary:   {test_res.get('summary')}")
            failures = test_res.get("failures") or []
            if failures:
                print(f"  Failures ({len(failures)}):")
                for f in failures[:5]:
                    name = f.get("name") or f.get("test") or "Unknown"
                    msg = (f.get("error") or f.get("message") or "")[:120]
                    print(f"    • {name}: {msg}")
            
            # Review
            review_res = res.get("review") or {}
            print(f"  Review Score:   {review_res.get('overall_score')}/10")
            print(f"  Review Status:  {'APPROVED' if review_res.get('approved') else 'REJECTED'}")
            defects = review_res.get("defects") or []
            if defects:
                print(f"  Defects ({len(defects)}):")
                for d in defects[:5]:
                    print(f"    • {str(d)[:120]}")
            feedback = review_res.get("feedback") or []
            if feedback:
                print(f"  Feedback:")
                for fb in feedback[:3]:
                    print(f"    • {str(fb)[:120]}")
                    
        except Exception as e:
            print(f"  (Could not parse result JSON: {e})")

    print("=" * 80 + "\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        list_sessions()
    elif args[0] in ("--last", "-l", "latest"):
        conn = get_connection()
        last = conn.cursor().execute("SELECT session_id FROM sessions ORDER BY rowid DESC LIMIT 1").fetchone()
        if last:
            view_session_details(last[0])
        else:
            print("No sessions found.")
    else:
        view_session_details(args[0])
