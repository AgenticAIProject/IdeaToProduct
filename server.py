import sys
import os
import json
import uuid
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# Add Agents to path
ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"
sys.path.append(str(ROOT_DIR / "Agents"))

from Agents.State_definition import AgentState
from Agents.graph import graph

# In-memory sessions store
sessions = {}
sessions_lock = threading.Lock()


def run_pipeline_thread(session_id: str, thread_id: str, resume_input=None):
    """Executes or resumes the LangGraph pipeline in a background worker thread."""
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 20
    }

    try:
        with sessions_lock:
            sessions[session_id]["is_running"] = True
            sessions[session_id]["status"] = "running"
            sessions[session_id]["error"] = None

        if resume_input:
            result = graph.invoke(resume_input, config=config)
        else:
            initial_state: AgentState = {
                "project_id": sessions[session_id]["project_id"],
                "user_id": "user_studio",
                "idea": sessions[session_id]["idea"],
                "clarification_questions": [],
                "user_answers": [],
                "clarification_round": 0,
                "requirements": {},
                "requirements_version": 0,
                "github_evidence": [],
                "design": {},
                "design_version": 0,
                "code": {},
                "code_version": 0,
                "generated_project_path": "",
                "test_results": {},
                "test_version": 0,
                "review": {},
                "review_version": 0,
                "documentation": {},
                "documentation_version": 0,
                "current_stage": "requirements",
                "workflow_status": "starting",
                "retry_count": {
                    "requirements": 0,
                    "design": 0,
                    "code": 0,
                    "test": 0,
                    "review": 0
                },
                "approval_status": "pending"
            }
            result = graph.invoke(initial_state, config=config)

        with sessions_lock:
            stage = result.get("current_stage", "documentation")
            workflow_status = result.get("workflow_status", "done")

            if workflow_status == "waiting_for_user":
                sessions[session_id]["status"] = "clarification"
                sessions[session_id]["stage"] = "clarification"
                sessions[session_id]["is_running"] = False
                sessions[session_id]["result"] = result
            else:
                sessions[session_id]["status"] = "done"
                sessions[session_id]["stage"] = stage
                sessions[session_id]["is_running"] = False
                sessions[session_id]["result"] = result

    except Exception as exc:
        with sessions_lock:
            sessions[session_id]["is_running"] = False
            sessions[session_id]["status"] = "error"
            sessions[session_id]["error"] = str(exc)


class PipelineServerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Handle API status polling: /api/status/<session_id>
        if path.startswith("/api/status/"):
            session_id = path.replace("/api/status/", "").strip()
            with sessions_lock:
                session = sessions.get(session_id)
                if not session:
                    self.send_response(404)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Session not found"}).encode("utf-8"))
                    return

                payload = {
                    "session_id": session_id,
                    "project_id": session.get("project_id"),
                    "is_running": session.get("is_running", False),
                    "status": session.get("status", "running"),
                    "stage": session.get("stage", "requirements"),
                    "error": session.get("error"),
                    "result": session.get("result"),
                }

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        # Serve frontend index.html for root path
        if path == "/" or not path:
            self.path = "/index.html"

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body = {}

        if path == "/api/start":
            idea = body.get("idea", "").strip()
            if not idea:
                self.send_response(400)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Idea cannot be empty"}).encode("utf-8"))
                return

            session_id = str(uuid.uuid4())
            project_id = body.get("project_id") or f"proj_{uuid.uuid4().hex[:6]}"
            thread_id = f"thread_{session_id}"

            with sessions_lock:
                sessions[session_id] = {
                    "session_id": session_id,
                    "project_id": project_id,
                    "thread_id": thread_id,
                    "idea": idea,
                    "is_running": True,
                    "status": "running",
                    "stage": "requirements",
                    "error": None,
                    "result": None,
                }

            # Launch pipeline in background thread
            worker = threading.Thread(
                target=run_pipeline_thread,
                args=(session_id, thread_id, None),
                daemon=True
            )
            worker.start()

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "session_id": session_id,
                "project_id": project_id,
                "status": "running"
            }).encode("utf-8"))
            return

        elif path == "/api/answer":
            session_id = body.get("session_id")
            answers = body.get("answers", [])

            with sessions_lock:
                session = sessions.get(session_id)
                if not session:
                    self.send_response(404)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Session not found"}).encode("utf-8"))
                    return

                thread_id = session["thread_id"]
                prev_result = session.get("result") or {}
                prior_answers = prev_result.get("user_answers", [])
                questions = prev_result.get("clarification_questions", [])

                collected_answers = []
                for i, ans in enumerate(answers):
                    q_text = questions[i] if i < len(questions) else f"Q{i+1}"
                    collected_answers.append(f"Q: {q_text}\nA: {ans}")

                resume_input = {
                    "user_answers": prior_answers + collected_answers,
                    "current_stage": "requirements",
                    "workflow_status": "running",
                }

                session["is_running"] = True
                session["status"] = "running"
                session["error"] = None

            worker = threading.Thread(
                target=run_pipeline_thread,
                args=(session_id, thread_id, resume_input),
                daemon=True
            )
            worker.start()

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "resumed", "session_id": session_id}).encode("utf-8"))
            return

        self.send_response(404)
        self._send_cors_headers()
        self.end_headers()


def run_server(port=8000):
    server_address = ("0.0.0.0", port)
    HTTPServer.allow_reuse_address = True
    httpd = HTTPServer(server_address, PipelineServerHandler)
    print(f"\n==================================================================")
    print(f"🚀 IdeaToProduct Unified Server running at: http://localhost:{port}")
    print(f"📁 Serving frontend files from: {FRONTEND_DIR}")
    print(f"🔗 Connected to LangGraph SDLC Agentic Pipeline")
    print(f"==================================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
