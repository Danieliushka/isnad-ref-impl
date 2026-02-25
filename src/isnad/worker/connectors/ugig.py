"""ugig.net platform connector — profile, gigs, reviews, rating."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

import httpx

from .base import BaseConnector, ConnectorResult, ConnectorMetrics

logger = logging.getLogger(__name__)


class UgigConnector(BaseConnector):
    platform_name = "ugig"

    BASE_URL = "https://ugig.net/api"

    def __init__(self):
        self.cookies_path = os.path.expanduser("~/.config/ugig/cookies.txt")

    def _extract_username(self, url: str) -> str | None:
        """Extract username from ugig URL like https://ugig.net/user/gendolf."""
        m = re.search(r"ugig\.net/(?:user|profile|u)/([A-Za-z0-9_.-]+)", url)
        return m.group(1) if m else None

    async def fetch(self, url: str) -> ConnectorResult:
        username = self._extract_username(url)
        if not username:
            return self._dead_result(url, "cannot parse ugig username from URL")

        headers = {}
        # Try to load cookies for authenticated requests
        try:
            if os.path.exists(self.cookies_path):
                with open(self.cookies_path) as f:
                    cookie_val = f.read().strip()
                if cookie_val:
                    headers["Cookie"] = cookie_val
        except Exception:
            pass

        try:
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                # Fetch profile
                resp = await client.get(f"{self.BASE_URL}/users/{username}")
                if resp.status_code != 200:
                    return self._dead_result(url, f"ugig API {resp.status_code}")
                data = resp.json()
                profile = data.get("profile", data)

                # Fetch reviews
                user_id = profile.get("id", "")
                reviews = []
                if user_id:
                    resp2 = await client.get(f"{self.BASE_URL}/reviews", params={"user_id": user_id})
                    if resp2.status_code == 200:
                        reviews = resp2.json().get("data", [])

        except httpx.HTTPError as e:
            logger.warning("ugig fetch failed for %s: %s", url, e)
            return self._dead_result(url, str(e))

        # Compute metrics
        avg_rating = float(profile.get("average_rating", 0))
        total_reviews = int(profile.get("total_reviews", 0))
        skills = profile.get("skills", [])

        # Activity score: based on last activity and job count
        activity_score = 0
        if profile.get("updated_at"):
            try:
                last_active = datetime.fromisoformat(
                    profile["updated_at"].replace("Z", "+00:00")
                )
                days_since = (datetime.now(timezone.utc) - last_active).days
                recency = max(0, 100 - days_since * 3)
                activity_score = min(recency, 100)
            except Exception:
                pass

        # Reputation: HONEST — no reviews = 0
        reputation_score = 0
        if total_reviews > 0 and avg_rating > 0:
            # Normalize to 0-100 (5-star scale)
            reputation_score = min(int(avg_rating / 5.0 * 100), 100)

        # Longevity
        longevity_days = 0
        if profile.get("created_at"):
            try:
                created = datetime.fromisoformat(
                    profile["created_at"].replace("Z", "+00:00")
                )
                longevity_days = (datetime.now(timezone.utc) - created).days
            except Exception:
                pass

        # Verification
        verification = "none"
        if profile.get("profile_completed") and total_reviews >= 3:
            verification = "verified"
        elif profile.get("profile_completed") or len(skills) >= 2:
            verification = "basic"

        # Evidence count
        evidence_count = total_reviews + len(reviews)

        return ConnectorResult(
            platform="ugig",
            url=url,
            alive=True,
            raw_data={
                "username": profile.get("username"),
                "average_rating": avg_rating,
                "total_reviews": total_reviews,
                "skills": skills,
                "profile_completed": profile.get("profile_completed", False),
                "has_avatar": bool(profile.get("avatar_url")),
                "created_at": profile.get("created_at"),
                "updated_at": profile.get("updated_at"),
                "reviews_sample": reviews[:5],
            },
            metrics=ConnectorMetrics(
                activity_score=activity_score,
                reputation_score=reputation_score,
                longevity_days=longevity_days,
                verification_level=verification,
                evidence_count=evidence_count,
            ),
        )
