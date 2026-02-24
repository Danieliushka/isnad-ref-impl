"""Platform connectors for fetching real reputation data from agent marketplaces."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class PlatformReputation:
    """Normalized reputation data from any platform."""
    platform: str
    username: str
    # Core metrics
    total_jobs: int = 0
    completed_jobs: int = 0
    cancelled_jobs: int = 0
    disputed_jobs: int = 0
    average_rating: float = 0.0
    total_reviews: int = 0
    # Financial
    total_earned: float = 0.0  # USD equivalent
    # Profile quality
    profile_completed: bool = False
    skills_count: int = 0
    has_avatar: bool = False
    has_portfolio: bool = False
    # Timestamps
    member_since: Optional[str] = None
    last_active: Optional[str] = None
    # Raw data for debugging
    raw: dict = field(default_factory=dict)


class UgigConnector:
    """Fetch reputation data from ugig.net API."""

    BASE_URL = "https://ugig.net/api"

    def __init__(self, cookies_path: str = "~/.config/ugig/cookies.txt"):
        self.cookies_path = os.path.expanduser(cookies_path)

    def _curl(self, endpoint: str) -> dict:
        """Execute curl with cookies and return JSON."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        try:
            result = subprocess.run(
                ["curl", "-s", "-b", self.cookies_path, url],
                capture_output=True, text=True, timeout=10
            )
            return json.loads(result.stdout)
        except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError):
            return {}

    def fetch_profile(self, username: str = "me") -> Optional[PlatformReputation]:
        """Fetch user profile and build reputation data."""
        if username == "me":
            data = self._curl("profile")
            profile = data.get("profile", data)
        else:
            data = self._curl(f"users/{username}")
            profile = data.get("profile", data)

        if not profile or "id" not in profile:
            return None

        # Fetch reviews separately
        reviews_data = self._curl(f"reviews?user_id={profile.get('id', '')}")
        reviews = reviews_data.get("data", [])

        # Fetch completed gigs/applications
        apps_data = self._curl("applications?status=completed")
        apps = apps_data.get("data", apps_data) if isinstance(apps_data, dict) else []

        return PlatformReputation(
            platform="ugig",
            username=profile.get("username", ""),
            total_jobs=len(apps) if isinstance(apps, list) else 0,
            completed_jobs=len([a for a in apps if isinstance(a, dict) and a.get("status") == "completed"]) if isinstance(apps, list) else 0,
            average_rating=float(profile.get("average_rating", 0)),
            total_reviews=int(profile.get("total_reviews", 0)),
            profile_completed=profile.get("profile_completed", False),
            skills_count=len(profile.get("skills", [])),
            has_avatar=bool(profile.get("avatar_url")),
            has_portfolio=bool(profile.get("portfolio_urls")),
            member_since=profile.get("created_at"),
            last_active=profile.get("updated_at"),
            raw=profile,
        )

    def fetch_by_wallet(self, wallet_address: str) -> Optional[PlatformReputation]:
        """Fetch reputation by wallet address (if supported)."""
        # ugig doesn't support wallet lookup yet
        return None


class GitHubConnector:
    """Fetch reputation data from GitHub API."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

    def _request(self, endpoint: str) -> dict:
        """Execute GitHub API request."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        cmd = ["curl", "-s", url]
        if self.token:
            cmd.extend(["-H", f"Authorization: Bearer {self.token}"])
        cmd.extend(["-H", "Accept: application/vnd.github+json"])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return json.loads(result.stdout)
        except (json.JSONDecodeError, subprocess.TimeoutExpired):
            return {}

    def fetch_profile(self, username: str) -> Optional[PlatformReputation]:
        """Fetch GitHub user profile as reputation data."""
        user = self._request(f"users/{username}")
        if "login" not in user:
            return None

        # Fetch repos for activity metrics
        repos = self._request(f"users/{username}/repos?per_page=100&sort=updated")
        if not isinstance(repos, list):
            repos = []

        # Count stars, forks across repos
        total_stars = sum(r.get("stargazers_count", 0) for r in repos)
        total_forks = sum(r.get("forks_count", 0) for r in repos)
        public_repos = len(repos)

        return PlatformReputation(
            platform="github",
            username=user.get("login", ""),
            total_jobs=public_repos,  # repos as "jobs"
            completed_jobs=len([r for r in repos if not r.get("archived", False)]),
            average_rating=min(total_stars / max(public_repos, 1), 5.0),  # normalized
            total_reviews=total_stars,  # stars as "reviews"
            profile_completed=bool(user.get("bio") and user.get("avatar_url")),
            skills_count=len(set(r.get("language", "") for r in repos if r.get("language"))),
            has_avatar=bool(user.get("avatar_url")),
            has_portfolio=bool(user.get("blog")),
            member_since=user.get("created_at"),
            last_active=user.get("updated_at"),
            raw={
                "followers": user.get("followers", 0),
                "following": user.get("following", 0),
                "public_repos": user.get("public_repos", 0),
                "total_stars": total_stars,
                "total_forks": total_forks,
            },
        )


class MoltlaunchConnector:
    """Fetch reputation data from Moltlaunch on-chain registry."""

    def __init__(self):
        self.cli = "mltl"

    def fetch_profile(self, agent_name: str) -> Optional[PlatformReputation]:
        """Fetch agent reputation from Moltlaunch."""
        try:
            result = subprocess.run(
                [self.cli, "reviews", "--agent", agent_name, "--json"],
                capture_output=True, text=True, timeout=15
            )
            reviews = json.loads(result.stdout) if result.stdout.strip() else {}
        except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError):
            reviews = {}

        try:
            result = subprocess.run(
                [self.cli, "earnings", "--json"],
                capture_output=True, text=True, timeout=15
            )
            earnings = json.loads(result.stdout) if result.stdout.strip() else {}
        except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError):
            earnings = {}

        review_list = reviews.get("reviews", [])
        total_earned = float(earnings.get("total", 0))

        return PlatformReputation(
            platform="moltlaunch",
            username=agent_name,
            total_reviews=len(review_list),
            average_rating=sum(r.get("rating", 0) for r in review_list) / max(len(review_list), 1),
            total_earned=total_earned,
            raw={"reviews": reviews, "earnings": earnings},
        )


class ClawkConnector:
    """Fetch social reputation from Clawk.ai."""

    BASE_URL = "https://www.clawk.ai/api/v1"

    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            creds_path = os.path.expanduser("~/.config/clawk/credentials.json")
            try:
                with open(creds_path) as f:
                    creds = json.load(f)
                    self.api_key = creds.get("api_key", "")
            except (FileNotFoundError, json.JSONDecodeError):
                self.api_key = ""
        else:
            self.api_key = api_key

    def _request(self, endpoint: str) -> dict:
        """Execute Clawk API request."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        try:
            result = subprocess.run(
                ["curl", "-s", url, "-H", f"Authorization: Bearer {self.api_key}"],
                capture_output=True, text=True, timeout=10
            )
            return json.loads(result.stdout)
        except (json.JSONDecodeError, subprocess.TimeoutExpired):
            return {}

    def fetch_profile(self, username: str) -> Optional[PlatformReputation]:
        """Fetch Clawk profile as reputation data."""
        profile = self._request(f"users/{username}")
        if not profile or "error" in profile:
            return None

        return PlatformReputation(
            platform="clawk",
            username=username,
            total_reviews=profile.get("followers", 0),
            profile_completed=bool(profile.get("bio")),
            has_avatar=bool(profile.get("avatar")),
            member_since=profile.get("created_at"),
            raw=profile,
        )


# ── Registry ──

CONNECTORS = {
    "ugig": UgigConnector,
    "github": GitHubConnector,
    "moltlaunch": MoltlaunchConnector,
    "clawk": ClawkConnector,
}


def get_connector(platform: str):
    """Get a connector instance by platform name."""
    cls = CONNECTORS.get(platform)
    if cls is None:
        raise ValueError(f"Unknown platform: {platform}. Available: {list(CONNECTORS.keys())}")
    return cls()
