import sys
import os
import json
import uuid
import threading
import io
import zipfile
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# Add Agents to path
ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"
sys.path.append(str(ROOT_DIR / "Agents"))

from Agents.State_definition import AgentState
from Agents.graph import graph
from Agents.ReleaseAgent import Release_Agent
import imports as agent_imports

# In-memory sessions store
sessions = {}
sessions_lock = threading.Lock()


def _session_project_dir(session):
    """Resolve a session's generated directory without allowing paths outside the workspace."""
    result = session.get("result") or {}
    code = result.get("code") or {}
    project_path = result.get("generated_project_path") or code.get("generated_project_path")
    if project_path:
        candidate = Path(project_path)
    else:
        project_id = str(session.get("project_id", ""))
        if not project_id or Path(project_id).name != project_id:
            return None
        candidate = ROOT_DIR / "generated_projects" / project_id

    root = (ROOT_DIR / "generated_projects").resolve()
    if candidate.is_symlink():
        return None
    candidate = candidate.resolve()
    if candidate.parent != root or not candidate.is_dir():
        return None
    return candidate


def list_generated_projects():
    """Return generated project folders and their relative file paths."""
    projects_dir = ROOT_DIR / "generated_projects"
    if not projects_dir.is_dir():
        return []

    projects = []
    ignored_dirs = {".git", "__pycache__", "node_modules", ".venv"}
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir() or project_dir.is_symlink():
            continue

        files = []
        for current_dir, child_dirs, filenames in os.walk(project_dir, followlinks=False):
            current_path = Path(current_dir)
            child_dirs[:] = [
                name for name in child_dirs
                if not name.startswith(".")
                and name not in ignored_dirs
                and not (current_path / name).is_symlink()
            ]
            for filename in filenames:
                path = current_path / filename
                if filename.startswith(".") or path.is_symlink() or not path.is_file():
                    continue
                files.append(path.relative_to(project_dir).as_posix())

        projects.append({
            "project_id": project_dir.name,
            "modified_at": project_dir.stat().st_mtime,
            "file_count": len(files),
            "files": sorted(files),
        })

    return sorted(projects, key=lambda project: project["modified_at"], reverse=True)


def run_release_thread(
    session_id: str,
    repo_url: str,
    github_token: str = "",
    commit_message: str = "",
):
    """Run an explicit user-approved release for a completed pipeline session."""
    try:
        with sessions_lock:
            session = sessions[session_id]
            release_state = dict(session.get("result") or {})
            release_state["approval_status"] = "approved"
            release_state["release_repo_url"] = repo_url
            if github_token:
                release_state["release_github_token"] = github_token
            if commit_message:
                release_state["release_commit_message"] = commit_message
            session["is_running"] = True
            session["status"] = "running"
            session["stage"] = "release"
            session["error"] = None

        release_update = Release_Agent(release_state)
        with sessions_lock:
            release_state.update(release_update)
            session = sessions[session_id]
            session["result"] = release_state
            session["is_running"] = False
            session["stage"] = "release"
            release_result = release_state.get("release") or {}
            if release_result.get("status") == "success":
                session["status"] = "done"
                session["error"] = None
            else:
                session["status"] = "error"
                session["error"] = (
                    release_result.get("error")
                    or release_result.get("reason")
                    or f"GitHub release did not succeed ({release_result.get('status', 'unknown')})."
                )
    except Exception as exc:
        with sessions_lock:
            sessions[session_id]["is_running"] = False
            sessions[session_id]["status"] = "error"
            sessions[session_id]["error"] = str(exc)


def run_pipeline_thread(session_id: str, thread_id: str, resume_input=None):
    """Executes or resumes the LangGraph pipeline in a background worker thread."""
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 20
    }

    try:
        with sessions_lock:
            session = sessions[session_id]
            if session.get("cancel_requested"):
                session["is_running"] = False
                session["status"] = "cancelled"
                return
            session["is_running"] = True
            session["status"] = "running"
            session["error"] = None

        if resume_input:
            graph_input = resume_input
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
                "token_usage": {},
                "release": {},
                "release_version": 0,
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
            graph_input = initial_state

        result = {}
        stream = iter(graph.stream(graph_input, config=config, stream_mode="updates"))
        while True:
            with sessions_lock:
                session = sessions[session_id]
                if session.get("cancel_requested"):
                    session["is_running"] = False
                    session["status"] = "cancelled"
                    session["result"] = dict(result) or session.get("result")
                    return

            try:
                update = next(stream)
            except StopIteration:
                break

            if not isinstance(update, dict):
                continue

            for node_name, node_update in update.items():
                if not isinstance(node_update, dict):
                    continue
                result.update(node_update)
                stage = node_update.get("current_stage", node_name)
                workflow_status = node_update.get("workflow_status", "running")
                with sessions_lock:
                    session = sessions[session_id]
                    session["stage"] = stage
                    session["result"] = dict(result)
                    if session.get("cancel_requested"):
                        session["is_running"] = False
                        session["status"] = "cancelled"
                        return
                    if workflow_status == "waiting_for_user":
                        session["status"] = "clarification"

        if not result:
            raise RuntimeError("Pipeline produced no agent updates.")

        with sessions_lock:
            session = sessions[session_id]
            if session.get("cancel_requested"):
                session["is_running"] = False
                session["status"] = "cancelled"
                session["result"] = dict(result)
                return
            stage = result.get("current_stage", "documentation")
            workflow_status = result.get("workflow_status", "done")

            if workflow_status == "waiting_for_user":
                session["status"] = "clarification"
                session["stage"] = "clarification"
                session["is_running"] = False
                session["result"] = result
            elif workflow_status == "failed":
                session["status"] = "error"
                session["stage"] = stage
                session["is_running"] = False
                session["result"] = result
                session["error"] = "Pipeline ended with a failed agent stage."
            else:
                session["status"] = "done"
                session["stage"] = stage
                session["is_running"] = False
                session["result"] = result

    except Exception as exc:
        with sessions_lock:
            session = sessions[session_id]
            session["is_running"] = False
            if session.get("cancel_requested"):
                session["status"] = "cancelled"
            else:
                session["status"] = "error"
                session["error"] = str(exc)


class PipelineServerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def end_headers(self):
        if self.path.split("?", 1)[0].endswith((".html", ".js", ".css")):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

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

        if path == "/api/sessions/active":
            with sessions_lock:
                active_session = next(
                    (session for session in reversed(list(sessions.values())) if session.get("is_running")),
                    None,
                )
                payload = {
                    "session": {
                        "session_id": active_session["session_id"],
                        "project_id": active_session.get("project_id"),
                        "is_running": active_session.get("is_running", False),
                        "status": active_session.get("status", "running"),
                        "stage": active_session.get("stage", "requirements"),
                        "error": active_session.get("error"),
                        "idea": active_session.get("idea", ""),
                        "result": active_session.get("result"),
                    } if active_session else None,
                }

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if path == "/api/projects":
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"projects": list_generated_projects()}).encode("utf-8"))
            return

        if path.startswith("/api/workspace/"):
            session_id = path.removeprefix("/api/workspace/").strip()
            with sessions_lock:
                session = sessions.get(session_id)
                if session:
                    project_dir = _session_project_dir(session)
                else:
                    project_dir = None

            if not session:
                self.send_response(404)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Session not found"}).encode("utf-8"))
                return
            if project_dir is None:
                self.send_response(404)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Generated project is not available"}).encode("utf-8"))
                return

            files = []
            ignored_dirs = {".git", "__pycache__", "node_modules", ".venv"}
            for current_dir, child_dirs, filenames in os.walk(project_dir, followlinks=False):
                current_path = Path(current_dir)
                child_dirs[:] = [
                    name for name in child_dirs
                    if not name.startswith(".")
                    and name not in ignored_dirs
                    and not (current_path / name).is_symlink()
                ]
                for filename in filenames:
                    file_path = current_path / filename
                    if filename.startswith(".") or file_path.is_symlink() or not file_path.is_file():
                        continue
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace") if file_path.stat().st_size <= 256_000 else ""
                    except OSError:
                        continue
                    files.append({
                        "path": file_path.relative_to(project_dir).as_posix(),
                        "content": content,
                    })
                    if len(files) >= 500:
                        break
                if len(files) >= 500:
                    break

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"files": files}).encode("utf-8"))
            return

        if path.startswith("/api/export/"):
            session_id = path.removeprefix("/api/export/").strip()
            with sessions_lock:
                session = sessions.get(session_id)
                project_dir = _session_project_dir(session) if session else None

            if not session or project_dir is None:
                self.send_response(404)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Generated project is not available"}).encode("utf-8"))
                return

            archive = io.BytesIO()
            ignored_dirs = {".git", "__pycache__", "node_modules", ".venv"}
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
                for current_dir, child_dirs, filenames in os.walk(project_dir, followlinks=False):
                    current_path = Path(current_dir)
                    child_dirs[:] = [
                        name for name in child_dirs
                        if not name.startswith(".")
                        and name not in ignored_dirs
                        and not (current_path / name).is_symlink()
                    ]
                    for filename in filenames:
                        file_path = current_path / filename
                        if filename.startswith(".") or file_path.is_symlink() or not file_path.is_file():
                            continue
                        zipped.write(file_path, file_path.relative_to(project_dir).as_posix())

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="generated-project.zip"')
            self.end_headers()
            self.wfile.write(archive.getvalue())
            return

        # Handle /api/models GET — return current model config
        if path == "/api/models":
            env_path = ROOT_DIR / ".env"
            env_models = {}
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("MODEL_") and "=" in line:
                        key, _, val = line.partition("=")
                        env_models[key.strip()] = val.strip()
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "models": env_models}).encode("utf-8"))
            return

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

        if path == "/api/models/runtime":
            models = body.get("models", {})
            if not isinstance(models, dict):
                self.send_response(400)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "models must be an object"}).encode("utf-8"))
                return
            agent_imports.set_runtime_models({
                str(agent): str(model)
                for agent, model in models.items()
            })
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "message": "Runtime models updated"}).encode("utf-8"))
            return

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
                    "cancel_requested": False,
                }

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

        elif path == "/api/stop":
            session_id = body.get("session_id")
            if not session_id:
                self.send_response(400)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "session_id is required"}).encode("utf-8"))
                return

            with sessions_lock:
                session = sessions.get(session_id)
                if not session:
                    self.send_response(404)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Session not found"}).encode("utf-8"))
                    return
                if not session.get("is_running"):
                    self.send_response(409)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "No execution is running"}).encode("utf-8"))
                    return

                session["cancel_requested"] = True
                session["status"] = "stopping"

            self.send_response(202)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "stopping", "session_id": session_id}).encode("utf-8"))
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
                session["cancel_requested"] = False

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

        elif path == "/api/release":
            session_id = body.get("session_id")
            repo_url = str(body.get("repo_url", "")).strip()
            github_token = str(body.get("github_token", "")).strip()
            commit_message = str(body.get("commit_message", "")).strip()
            with sessions_lock:
                session = sessions.get(session_id)
                if not session:
                    self.send_response(404)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Session not found"}).encode("utf-8"))
                    return
                if session.get("is_running"):
                    self.send_response(409)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Pipeline is still running"}).encode("utf-8"))
                    return
                result = session.get("result") or {}
                if result.get("approval_status") != "approved":
                    self.send_response(403)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": "Release requires an approved quality review"
                    }).encode("utf-8"))
                    return
                if not repo_url:
                    repo_url = os.environ.get("GITHUB_REPO_URL", "")
                if not repo_url:
                    self.send_response(400)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Repository URL is required"}).encode("utf-8"))
                    return
                if not github_token and not any(
                    os.environ.get(name) for name in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT")
                ):
                    self.send_response(400)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": "A GitHub token with repository Contents write access is required to publish."
                    }).encode("utf-8"))
                    return
                session["is_running"] = True
                session["status"] = "running"
                session["stage"] = "release"
                session["error"] = None

            worker = threading.Thread(
                target=run_release_thread,
                args=(session_id, repo_url, github_token, commit_message),
                daemon=True,
            )
            worker.start()
            self.send_response(202)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "release_started", "session_id": session_id}).encode("utf-8"))
            return

        self.send_response(404)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": False, "error": f"Unknown endpoint: {path}"}).encode("utf-8"))


def run_server(port=8000):
    server_address = ("0.0.0.0", port)
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
