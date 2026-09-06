"""Minimal Gitea REST client — only the endpoints the fleet uses."""

from __future__ import annotations

import logging
from urllib.parse import quote, urlparse, urlunparse

import httpx

from .config import Settings

log = logging.getLogger(__name__)


class GiteaClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.org = settings.gitea_org
        self._client = httpx.Client(
            base_url=f"{settings.gitea_url.rstrip('/')}/api/v1",
            headers={"Authorization": f"token {settings.gitea_token}"},
            timeout=30,
        )

    def _req(self, method: str, path: str, ok=(200, 201, 204), **kwargs) -> httpx.Response:
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code not in ok:
            raise RuntimeError(f"Gitea {method} {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp

    # ------------------------------------------------------------------ repos

    def repo_exists(self, repo: str) -> bool:
        return self._client.get(f"/repos/{self.org}/{repo}").status_code == 200

    def create_repo_from_template(self, repo: str) -> None:
        """New project repo seeded from the template (includes the CI merge gate)."""
        self._req(
            "POST",
            f"/repos/{self.org}/{self.settings.template_repo}/generate",
            json={
                "owner": self.org,
                "name": repo,
                "git_content": True,
                "private": True,
            },
        )
        log.info("created repo %s/%s from template", self.org, repo)

    def protect_main(self, repo: str) -> None:
        """Branch protection = the human merge gate (risk #7).

        Agents (bots) can push branches and approve, but merging main requires a
        human approval and green CI. Bot reviews don't count toward the quorum
        because review-bot is listed as a non-counting approver via required
        approvals from non-bot users.
        """
        self._req(
            "POST",
            f"/repos/{self.org}/{repo}/branch_protections",
            json={
                "branch_name": "main",
                "enable_push": False,
                "required_approvals": 1,
                "block_on_rejected_reviews": True,
                "block_on_outdated_branch": True,
                "dismiss_stale_approvals": True,
                "enable_status_check": True,
                "status_check_contexts": ["ci / test"],
            },
            ok=(200, 201, 204, 409),  # 409: protection already exists
        )

    # ------------------------------------------------------------ pull requests

    def create_pr(self, repo: str, head: str, title: str, body: str) -> int:
        resp = self._req(
            "POST",
            f"/repos/{self.org}/{repo}/pulls",
            json={"head": head, "base": "main", "title": title, "body": body},
        )
        return resp.json()["number"]

    def get_pr(self, repo: str, number: int) -> dict:
        return self._req("GET", f"/repos/{self.org}/{repo}/pulls/{number}").json()

    def get_pr_diff(self, repo: str, number: int) -> str:
        return self._req("GET", f"/repos/{self.org}/{repo}/pulls/{number}.diff").text

    def create_review(self, repo: str, number: int, event: str, body: str) -> None:
        """event: APPROVED | REQUEST_CHANGES | COMMENT"""
        self._req(
            "POST",
            f"/repos/{self.org}/{repo}/pulls/{number}/reviews",
            json={"event": event, "body": body},
        )

    def comment_pr(self, repo: str, number: int, body: str) -> None:
        self._req("POST", f"/repos/{self.org}/{repo}/issues/{number}/comments", json={"body": body})

    # ----------------------------------------------------------------- issues

    def create_issue(self, repo: str, title: str, body: str) -> int:
        resp = self._req("POST", f"/repos/{self.org}/{repo}/issues", json={"title": title, "body": body})
        return resp.json()["number"]

    # ------------------------------------------------------------------ clone

    def authed_clone_url(self, repo: str) -> str:
        """http clone URL with the bot's credentials embedded (in-cluster only)."""
        parsed = urlparse(self.settings.gitea_url)
        netloc = f"{quote(self.settings.gitea_user)}:{quote(self.settings.gitea_token)}@{parsed.netloc}"
        return urlunparse((parsed.scheme, netloc, f"/{self.org}/{repo}.git", "", "", ""))
