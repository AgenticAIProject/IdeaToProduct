"""
mcp_github_connector.py - Model Context Protocol (MCP) connector for GitHub issue grounding.

Implements the MCP specification (tools/list and tools/call JSON-RPC standard)
to connect requirement agents to GitHub issues and developer bug reports.
"""

import os
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent


class MCPGitHubConnector:
    """
    Model Context Protocol (MCP) connector client.
    Exposes standard MCP tool definitions and handles JSON-RPC tool calls for GitHub data grounding.
    """

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self):
        self.server_url = os.environ.get("GITHUB_MCP_SERVER_URL", "").strip()

    def list_tools(self) -> list[dict[str, Any]]:
        """Return available MCP tool definitions following the MCP specification."""
        return [
            {
                "name": "get_github_issues",
                "description": "MCP connector to retrieve developer bug reports, closed issues, and edge cases from GitHub for requirement grounding.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Domain and technical keywords to search for developer issues."
                        },
                        "limit": {
                            "type": "integer",
                            "default": 3,
                            "description": "Maximum number of issues to retrieve."
                        }
                    },
                    "required": ["keywords"]
                }
            }
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute an MCP tool call adhering to standard MCP JSON-RPC protocol format:
        { "content": [ { "type": "text", "text": "..." } ], "isError": False }
        """
        if name != "get_github_issues":
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown MCP tool: {name}"}]
            }

        keywords = arguments.get("keywords", [])
        limit = arguments.get("limit", 3)
        query = " ".join(keywords[:3]).strip()

        print(f"  [MCP Connector] Invoking MCP tool '{name}' (keywords={keywords[:3]})...")

        issues = []
        source = "gh_archive_samples (MCP embedded)"

        # 1. Check curated GH Archive dataset (instant, reliable)
        archive_path = DATA_DIR / "github_archive_samples.json"
        if archive_path.exists():
            try:
                archive = json.loads(archive_path.read_text(encoding="utf-8"))
                query_words = set(query.lower().split() + [kw.lower() for kw in keywords])
                scored_issues = []
                for entry in archive:
                    entry_kws = set(entry.get("keywords", []))
                    score = len(query_words.intersection(entry_kws))
                    if score > 0:
                        scored_issues.append((score, entry))
                if scored_issues:
                    scored_issues.sort(key=lambda x: x[0], reverse=True)
                    issues = [
                        {
                            "repo": item["repo"],
                            "title": item["title"],
                            "body": item["body"][:250],
                            "labels": item["labels"]
                        }
                        for _, item in scored_issues[:limit]
                    ]
            except Exception as exc:
                print(f"  [MCP Connector] Archive read warning: {exc}")

        # 2. Try live GitHub API if no local matches and query exists
        if not issues and query:
            try:
                encoded_q = urllib.parse.quote(f"{query} is:issue state:closed")
                url = f"https://api.github.com/search/issues?q={encoded_q}&sort=reactions&per_page={limit}"
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "IdeaToProduct-MCP-Client/1.0",
                        "Accept": "application/vnd.github.v3+json"
                    }
                )
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for item in data.get("items", [])[:limit]:
                        issues.append({
                            "repo": item.get("repository_url", "").split("/")[-1] or "github",
                            "title": item.get("title", ""),
                            "body": (item.get("body") or "")[:250],
                            "labels": [lbl.get("name", "") for lbl in item.get("labels", [])][:3]
                        })
                    if issues:
                        source = "live_github_api (MCP remote)"
            except Exception:
                pass

        formatted_text = "\n".join(
            f"- [{issue.get('repo')}] {issue.get('title')}: {issue.get('body', '')[:150]}"
            for issue in issues
        ) if issues else "No specific edge cases retrieved."

        # Return standardized MCP tool response envelope
        return {
            "isError": False,
            "source": source,
            "issue_count": len(issues),
            "issues": issues,
            "content": [
                {
                    "type": "text",
                    "text": formatted_text
                }
            ]
        }


# Singleton MCP Connector instance
mcp_github = MCPGitHubConnector()
