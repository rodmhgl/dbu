"""GitHub REST API client for the scaffold workflow.

Handles branch creation, file commits, and PR creation using the
GitHub Contents API and Git Refs API.
"""

import base64
from typing import Dict, Optional

import requests as http_requests


class GitHubClient:
    def __init__(self, token: str, repo: str):
        self.api_base = f"https://api.github.com/repos/{repo}"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.repo = repo
        self.token = token

    def get_default_branch_sha(self) -> str:
        resp = http_requests.get(
            f"{self.api_base}/git/ref/heads/main",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()["object"]["sha"]

    def create_branch(self, branch_name: str, sha: str) -> None:
        resp = http_requests.post(
            f"{self.api_base}/git/refs",
            headers=self.headers,
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
        )
        resp.raise_for_status()

    def create_or_update_file(
        self, branch: str, path: str, content: str, message: str
    ) -> None:
        encoded = base64.b64encode(content.encode()).decode()

        sha = self._get_file_sha(branch, path)

        payload: dict = {
            "branch": branch,
            "content": encoded,
            "message": message,
        }
        if sha is not None:
            payload["sha"] = sha

        resp = http_requests.put(
            f"{self.api_base}/contents/{path}",
            headers=self.headers,
            json=payload,
        )
        resp.raise_for_status()

    def get_file_content(self, branch: str, path: str) -> Optional[str]:
        resp = http_requests.get(
            f"{self.api_base}/contents/{path}",
            headers=self.headers,
            params={"ref": branch},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["content"]).decode()

    def create_pull_request(self, branch: str, title: str, body: str) -> str:
        resp = http_requests.post(
            f"{self.api_base}/pulls",
            headers=self.headers,
            json={
                "base": "main",
                "body": body,
                "head": branch,
                "title": title,
            },
        )
        resp.raise_for_status()
        return resp.json()["html_url"]

    def create_repo(
        self, name: str, description: str = "", private: bool = False
    ) -> str:
        """Create a new GitHub repository under the authenticated user.

        Returns the html_url of the created repository.
        """
        resp = http_requests.post(
            "https://api.github.com/user/repos",
            headers=self.headers,
            json={
                "auto_init": True,
                "description": description,
                "name": name,
                "private": private,
            },
        )
        resp.raise_for_status()
        return resp.json()["html_url"]

    def commit_files_to_repo(
        self, repo: str, files: Dict[str, str], message: str
    ) -> None:
        """Commit multiple files to a repo in a single atomic commit.

        Uses the Git Trees API: create blobs -> create tree -> create commit
        -> update ref.  The ``repo`` param is the full ``owner/repo`` string
        (which may differ from ``self.repo``).
        """
        api_base = f"https://api.github.com/repos/{repo}"

        # Get HEAD sha of the default branch
        ref_resp = http_requests.get(
            f"{api_base}/git/ref/heads/main",
            headers=self.headers,
        )
        ref_resp.raise_for_status()
        head_sha = ref_resp.json()["object"]["sha"]

        # Get the tree sha for the HEAD commit
        commit_resp = http_requests.get(
            f"{api_base}/git/commits/{head_sha}",
            headers=self.headers,
        )
        commit_resp.raise_for_status()
        base_tree_sha = commit_resp.json()["tree"]["sha"]

        # Create blobs and build tree entries
        tree_entries = []
        for path, content in sorted(files.items()):
            blob_resp = http_requests.post(
                f"{api_base}/git/blobs",
                headers=self.headers,
                json={"content": content, "encoding": "utf-8"},
            )
            blob_resp.raise_for_status()
            blob_sha = blob_resp.json()["sha"]

            tree_entries.append(
                {
                    "mode": "100644",
                    "path": path,
                    "sha": blob_sha,
                    "type": "blob",
                }
            )

        # Create tree
        tree_resp = http_requests.post(
            f"{api_base}/git/trees",
            headers=self.headers,
            json={"base_tree": base_tree_sha, "tree": tree_entries},
        )
        tree_resp.raise_for_status()
        new_tree_sha = tree_resp.json()["sha"]

        # Create commit
        new_commit_resp = http_requests.post(
            f"{api_base}/git/commits",
            headers=self.headers,
            json={
                "message": message,
                "parents": [head_sha],
                "tree": new_tree_sha,
            },
        )
        new_commit_resp.raise_for_status()
        new_commit_sha = new_commit_resp.json()["sha"]

        # Update ref
        update_ref_resp = http_requests.patch(
            f"{api_base}/git/refs/heads/main",
            headers=self.headers,
            json={"sha": new_commit_sha},
        )
        update_ref_resp.raise_for_status()

    def _get_file_sha(self, branch: str, path: str) -> Optional[str]:
        resp = http_requests.get(
            f"{self.api_base}/contents/{path}",
            headers=self.headers,
            params={"ref": branch},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()["sha"]
