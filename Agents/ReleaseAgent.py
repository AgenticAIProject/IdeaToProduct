import os
import shutil
import subprocess
import base64
from pathlib import Path
from typing import cast

try:
    from State_definition import AgentState
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from Agents.State_definition import AgentState


def _git(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        check=False,
    )


def _next_release_version(state: AgentState) -> int:
    return cast(int, state.get("release_version", 0)) + 1


def Release_Agent(state: AgentState) -> dict:
    """
    Release Agent (Stage 7):
    - Requires the project to be approval_status == "approved".
    - Pushes the generated project folder to GitHub using GITHUB_REPO_URL.
    - Deletes the generated project from disk after a successful push.
    """
    print("\nRelease Agent preparing approved project for GitHub...")

    approval_status = state.get("approval_status", "pending")
    if approval_status != "approved":
        return {
            "release": {
                "status": "blocked",
                "reason": "Release requires user approval. Current approval_status is not 'approved'.",
            },
            "release_version": _next_release_version(state),
            "current_stage": "release",
            "workflow_status": "blocked_by_governance",
        }

    project_id = state.get("project_id") or "project"
    generated_project_path = state.get("generated_project_path")
    project_dir = Path(generated_project_path) if generated_project_path else None
    if project_dir is None or not project_dir.exists():
        project_dir = Path(__file__).resolve().parent.parent / "generated_projects" / project_id

    if not project_dir.exists():
        return {
            "release": {
                "status": "not_found",
                "reason": f"Generated project folder does not exist: {project_dir}",
            },
            "release_version": _next_release_version(state),
            "current_stage": "release",
            "workflow_status": "failed",
        }

    github_token = (
        str(state.get("release_github_token", "")).strip()
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_PAT")
    )
    has_credentials = bool(github_token)

    if not has_credentials:
        print(f"  [Release Agent] GitHub credentials (GITHUB_TOKEN) not present. Keeping project folder on disk at: {project_dir}")
        return {
            "release": {
                "status": "kept_local",
                "reason": "GitHub credentials not present. Project preserved on disk.",
                "project_id": project_id,
                "project_path": str(project_dir),
                "deleted_from_disk": False,
                "pushed_to_github": False,
            },
            "release_version": _next_release_version(state),
            "current_stage": "release",
            "workflow_status": "released_local",
        }

    requested_repo_url = state.get("release_repo_url")
    repo_url = (
        str(requested_repo_url).strip()
        if requested_repo_url
        else os.environ.get("GITHUB_REPO_URL")
        or os.environ.get("GITHUB_REMOTE_URL")
        or "https://github.com/ShivarajChougala15/temp.git"
    )
    os.environ["GITHUB_REPO_URL"] = repo_url
    os.environ["GITHUB_REMOTE_URL"] = repo_url

    try:
        if not (project_dir / ".git").exists():
            init_result = _git(project_dir, "init")
            if init_result.returncode != 0:
                raise RuntimeError(f"git init failed: {init_result.stderr.strip()}")

        config_name = _git(project_dir, "config", "user.name", "IdeaToProduct Bot")
        config_email = _git(project_dir, "config", "user.email", "bot@ideatoproduct.local")
        if config_name.returncode != 0 or config_email.returncode != 0:
            raise RuntimeError("git config failed")

        remote_check = _git(project_dir, "remote", "get-url", "origin")
        if remote_check.returncode == 0:
            set_result = _git(project_dir, "remote", "set-url", "origin", repo_url)
            if set_result.returncode != 0:
                raise RuntimeError(f"git remote set-url failed: {set_result.stderr.strip()}")
        else:
            add_result = _git(project_dir, "remote", "add", "origin", repo_url)
            if add_result.returncode != 0:
                raise RuntimeError(f"git remote add failed: {add_result.stderr.strip()}")

        add_result = _git(project_dir, "add", ".")
        if add_result.returncode != 0:
            raise RuntimeError(f"git add failed: {add_result.stderr.strip()}")

        status_result = _git(project_dir, "status", "--short")
        if status_result.stdout.strip():
            commit_message = (
                str(state.get("release_commit_message", "")).strip()
                or "Release approved project"
            )
            commit_result = _git(project_dir, "commit", "-m", commit_message)
            if commit_result.returncode != 0:
                raise RuntimeError(f"git commit failed: {commit_result.stderr.strip() or commit_result.stdout.strip()}")

        push_args = ["push", "-u", "origin", "HEAD"]
        if github_token and repo_url.startswith("https://"):
            credentials = base64.b64encode(
                f"x-access-token:{github_token}".encode("utf-8")
            ).decode("ascii")
            push_args = [
                "-c",
                f"http.extraheader=Authorization: Basic {credentials}",
                *push_args,
            ]
        push_result = _git(project_dir, *push_args)
        if push_result.returncode != 0:
            push_error = push_result.stderr.strip() or push_result.stdout.strip()
            if "authentication failed" in push_error.lower() or "403" in push_error:
                raise RuntimeError(
                    "GitHub authentication failed. Revoke the exposed token, create a new "
                    "token with repository Contents read/write permission, and retry."
                )
            raise RuntimeError(f"git push failed: {push_error}")

        # Successfully pushed to GitHub -> remove project folder from disk
        shutil.rmtree(project_dir)
        print(f"  [Release Agent] Successfully pushed to GitHub. Removed project folder from disk: {project_dir}")

        return {
            "release": {
                "status": "success",
                "project_id": project_id,
                "project_path": str(project_dir),
                "remote_url": repo_url,
                "deleted_from_disk": True,
                "pushed_to_github": True,
            },
            "release_version": _next_release_version(state),
            "current_stage": "release",
            "workflow_status": "released",
        }

    except Exception as exc:  # noqa: BLE001
        print(f"  [Release Agent] Git release failed: {exc}. Preserving project files on disk at: {project_dir}")
        return {
            "release": {
                "status": "failed",
                "project_id": project_id,
                "project_path": str(project_dir),
                "remote_url": repo_url,
                "deleted_from_disk": False,
                "error": str(exc),
            },
            "release_version": _next_release_version(state),
            "current_stage": "release",
            "workflow_status": "failed",
        }
