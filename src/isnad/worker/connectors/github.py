"""GitHub platform connector — fetches public repos, stars, commits, languages."""

from __future__ import annotations

import logging
import math
import os
import re
from datetime import datetime, timezone

import httpx

from .base import BaseConnector, ConnectorResult, ConnectorMetrics

logger = logging.getLogger(__name__)


class GitHubConnector(BaseConnector):
    platform_name = "github"

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

    def _extract_username(self, url: str) -> str | None:
        """Extract GitHub username from URL."""
        m = re.search(r"github\.com/([A-Za-z0-9_.-]+)", url)
        return m.group(1) if m else None

    async def fetch(self, url: str) -> ConnectorResult:
        username = self._extract_username(url)
        if not username:
            return self._dead_result(url, "cannot parse GitHub username from URL")

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                # Fetch user profile
                resp = await client.get(f"https://api.github.com/users/{username}")
                if resp.status_code != 200:
                    return self._dead_result(url, f"GitHub API {resp.status_code}")
                user = resp.json()

                # Fetch repos
                resp2 = await client.get(
                    f"https://api.github.com/users/{username}/repos",
                    params={"per_page": 100, "sort": "updated"},
                )
                repos = resp2.json() if resp2.status_code == 200 and isinstance(resp2.json(), list) else []

        except httpx.HTTPError as e:
            logger.warning("GitHub fetch failed for %s: %s", url, e)
            return self._dead_result(url, str(e))

        # Compute metrics
        total_stars = sum(r.get("stargazers_count", 0) for r in repos)
        total_forks = sum(r.get("forks_count", 0) for r in repos)
        public_repos = len(repos)
        languages = list({r.get("language") for r in repos if r.get("language")})

        # Activity score: based on recency + repo count
        activity_score = 0
        if repos:
            # Most recent push
            try:
                last_push = max(
                    (datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
                     for r in repos if r.get("pushed_at")),
                    default=None,
                )
                if last_push:
                    days_since = (datetime.now(timezone.utc) - last_push).days
                    recency = max(0, 100 - days_since * 2)  # drops to 0 after 50 days
                    repo_factor = min(public_repos / 10, 1.0) * 30
                    activity_score = min(int(recency * 0.7 + repo_factor), 100)
            except Exception:
                pass

        # Reputation score: stars-based, evidence-based, HONEST
        # No stars = 0 reputation
        if total_stars == 0:
            reputation_score = 0
        else:
            reputation_score = min(int(math.log2(total_stars + 1) * 10), 100)

        # Longevity
        longevity_days = 0
        if user.get("created_at"):
            try:
                created = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
                longevity_days = (datetime.now(timezone.utc) - created).days
            except Exception:
                pass

        # Verification level
        verification = "none"
        if user.get("bio") and user.get("email"):
            verification = "verified"
        elif user.get("bio") or public_repos > 5:
            verification = "basic"

        # Evidence count: each repo with stars or forks is evidence
        evidence_count = sum(1 for r in repos if r.get("stargazers_count", 0) > 0 or r.get("forks_count", 0) > 0)

        return ConnectorResult(
            platform="github",
            url=url,
            alive=True,
            raw_data={
                "username": user.get("login"),
                "name": user.get("name"),
                "bio": user.get("bio"),
                "followers": user.get("followers", 0),
                "following": user.get("following", 0),
                "public_repos": public_repos,
                "total_stars": total_stars,
                "total_forks": total_forks,
                "languages": languages,
                "created_at": user.get("created_at"),
                "updated_at": user.get("updated_at"),
            },
            metrics=ConnectorMetrics(
                activity_score=activity_score,
                reputation_score=reputation_score,
                longevity_days=longevity_days,
                verification_level=verification,
                evidence_count=evidence_count,
            ),
        )
