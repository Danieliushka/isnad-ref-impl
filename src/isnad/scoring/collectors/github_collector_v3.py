"""GitHub data collector for scoring v3 — Events API, orgs, followers."""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

import aiohttp

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


@dataclass
class GitHubData:
    username: str = ""
    verified: bool = False
    account_age_days: int = 0
    followers: int = 0
    orgs: int = 0
    commits_90d: int = 0
    total_stars: int = 0
    last_push_at: datetime | None = None
    created_at: datetime | None = None


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


async def fetch_github_data(username: str) -> GitHubData:
    """Fetch all GitHub data needed for v3 scoring."""
    if not username:
        return GitHubData()

    data = GitHubData(username=username)
    timeout = aiohttp.ClientTimeout(total=15)

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=_headers()) as session:
            # Profile
            async with session.get(f"{GITHUB_API}/users/{username}") as resp:
                if resp.status != 200:
                    return data
                profile = await resp.json()
                data.verified = True
                data.followers = profile.get("followers", 0)
                created = _parse_dt(profile.get("created_at"))
                data.created_at = created
                if created:
                    data.account_age_days = (datetime.now(timezone.utc) - created).days

            # Repos (stars + last push)
            async with session.get(
                f"{GITHUB_API}/users/{username}/repos",
                params={"sort": "stars", "per_page": 30},
            ) as resp:
                if resp.status == 200:
                    repos = await resp.json()
                    data.total_stars = sum(r.get("stargazers_count", 0) for r in repos)
                    for r in repos:
                        pushed = _parse_dt(r.get("pushed_at"))
                        if pushed and (data.last_push_at is None or pushed > data.last_push_at):
                            data.last_push_at = pushed

            # Orgs
            async with session.get(f"{GITHUB_API}/users/{username}/orgs") as resp:
                if resp.status == 200:
                    orgs = await resp.json()
                    data.orgs = len(orgs)

            # Events (commits last 90d)
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            commits = 0
            async with session.get(
                f"{GITHUB_API}/users/{username}/events",
                params={"per_page": 100},
            ) as resp:
                if resp.status == 200:
                    events = await resp.json()
                    for event in events:
                        if event.get("type") == "PushEvent":
                            created = _parse_dt(event.get("created_at"))
                            if created and created > cutoff:
                                commits += event.get("payload", {}).get("size", 1)
            data.commits_90d = commits

    except Exception as e:
        logger.warning("GitHub fetch failed for %s: %s", username, e)

    return data
