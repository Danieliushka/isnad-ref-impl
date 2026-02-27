"""GitHub data collector — public API, no token required (60 req/hr)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
TIMEOUT = aiohttp.ClientTimeout(total=15)


class GitHubData:
    """Parsed GitHub profile data."""

    def __init__(
        self,
        username: str,
        account_created: Optional[datetime] = None,
        public_repos: int = 0,
        followers: int = 0,
        total_stars: int = 0,
        last_push: Optional[datetime] = None,
        has_email: bool = False,
        orgs_count: int = 0,
    ):
        self.username = username
        self.account_created = account_created
        self.public_repos = public_repos
        self.followers = followers
        self.total_stars = total_stars
        self.last_push = last_push
        self.has_email = has_email
        self.orgs_count = orgs_count

    @property
    def account_age_days(self) -> int:
        if not self.account_created:
            return 0
        return max(0, (datetime.now(timezone.utc) - self.account_created).days)

    @property
    def days_since_last_push(self) -> Optional[int]:
        if not self.last_push:
            return None
        return max(0, (datetime.now(timezone.utc) - self.last_push).days)

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "account_age_days": self.account_age_days,
            "public_repos": self.public_repos,
            "followers": self.followers,
            "total_stars": self.total_stars,
            "days_since_last_push": self.days_since_last_push,
            "has_email": self.has_email,
            "orgs_count": self.orgs_count,
        }


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


async def fetch_github_data(username: str) -> Optional[GitHubData]:
    """Fetch GitHub profile + repos data for a username. Returns None on failure."""
    try:
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "isnad-trust-engine/1.0"}
        async with aiohttp.ClientSession(timeout=TIMEOUT, headers=headers) as session:
            # Fetch user profile
            async with session.get(f"{GITHUB_API}/users/{username}") as resp:
                if resp.status != 200:
                    logger.warning("GitHub user %s: HTTP %d", username, resp.status)
                    return None
                user = await resp.json()

            data = GitHubData(
                username=username,
                account_created=_parse_dt(user.get("created_at")),
                public_repos=user.get("public_repos", 0),
                followers=user.get("followers", 0),
                has_email=bool(user.get("email")),
            )

            # Fetch repos to get total stars and last push
            total_stars = 0
            last_push = None
            page = 1
            while page <= 3:  # Max 3 pages (90 repos) to stay within rate limits
                async with session.get(
                    f"{GITHUB_API}/users/{username}/repos",
                    params={"per_page": 30, "page": page, "sort": "pushed"},
                ) as resp:
                    if resp.status != 200:
                        break
                    repos = await resp.json()
                    if not repos:
                        break
                    for repo in repos:
                        total_stars += repo.get("stargazers_count", 0)
                        pushed = _parse_dt(repo.get("pushed_at"))
                        if pushed and (last_push is None or pushed > last_push):
                            last_push = pushed
                    page += 1

            data.total_stars = total_stars
            data.last_push = last_push

            # Fetch orgs count
            try:
                async with session.get(f"{GITHUB_API}/users/{username}/orgs") as resp:
                    if resp.status == 200:
                        orgs = await resp.json()
                        data.orgs_count = len(orgs)
            except Exception:
                pass

            return data

    except Exception as e:
        logger.error("GitHub fetch failed for %s: %s", username, e)
        return None


def extract_github_username(platforms: list[dict]) -> Optional[str]:
    """Extract GitHub username from agent's platform list."""
    for p in platforms:
        if p.get("name", "").lower() == "github":
            url = p.get("url", "")
            if not url:
                continue
            # Handle various URL formats
            url = url.rstrip("/")
            # https://github.com/username or https://github.com/username/repo
            parts = url.replace("https://github.com/", "").replace("http://github.com/", "").split("/")
            if parts and parts[0]:
                username = parts[0]
                # Skip "apps" prefix
                if username == "apps" and len(parts) > 1:
                    return parts[1]
                return username
    return None
