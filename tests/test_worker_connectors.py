"""Tests for platform worker connectors with mocked HTTP responses."""

import json
import pytest
import httpx
import respx

from isnad.worker.connectors.github import GitHubConnector
from isnad.worker.connectors.ugig import UgigConnector
from isnad.worker.connectors.generic import GenericConnector


# ── GitHub Connector Tests ──

@pytest.mark.asyncio
async def test_github_connector_success():
    """GitHub connector returns proper metrics for a valid profile."""
    connector = GitHubConnector(token="")

    with respx.mock:
        respx.get("https://api.github.com/users/testuser").mock(
            return_value=httpx.Response(200, json={
                "login": "testuser",
                "name": "Test User",
                "bio": "A developer",
                "email": "test@example.com",
                "followers": 50,
                "following": 10,
                "public_repos": 15,
                "created_at": "2020-01-01T00:00:00Z",
                "updated_at": "2026-02-20T00:00:00Z",
                "avatar_url": "https://avatars.githubusercontent.com/u/1",
            })
        )
        respx.get("https://api.github.com/users/testuser/repos").mock(
            return_value=httpx.Response(200, json=[
                {
                    "name": "repo1",
                    "stargazers_count": 100,
                    "forks_count": 20,
                    "language": "Python",
                    "archived": False,
                    "pushed_at": "2026-02-20T00:00:00Z",
                },
                {
                    "name": "repo2",
                    "stargazers_count": 5,
                    "forks_count": 1,
                    "language": "Rust",
                    "archived": False,
                    "pushed_at": "2026-01-15T00:00:00Z",
                },
            ])
        )

        result = await connector.fetch("https://github.com/testuser")

    assert result["alive"] is True
    assert result["platform"] == "github"
    assert result["metrics"]["reputation_score"] > 0  # has stars
    assert result["metrics"]["activity_score"] > 0
    assert result["metrics"]["evidence_count"] == 2  # both repos have stars
    assert result["raw_data"]["total_stars"] == 105


@pytest.mark.asyncio
async def test_github_connector_no_stars():
    """GitHub with no stars = reputation 0."""
    connector = GitHubConnector(token="")

    with respx.mock:
        respx.get("https://api.github.com/users/newuser").mock(
            return_value=httpx.Response(200, json={
                "login": "newuser",
                "created_at": "2026-02-01T00:00:00Z",
                "updated_at": "2026-02-01T00:00:00Z",
            })
        )
        respx.get("https://api.github.com/users/newuser/repos").mock(
            return_value=httpx.Response(200, json=[
                {"name": "empty", "stargazers_count": 0, "forks_count": 0,
                 "language": None, "archived": False, "pushed_at": "2026-02-01T00:00:00Z"},
            ])
        )

        result = await connector.fetch("https://github.com/newuser")

    assert result["alive"] is True
    assert result["metrics"]["reputation_score"] == 0  # HONEST: no stars = 0


@pytest.mark.asyncio
async def test_github_connector_404():
    """GitHub 404 = dead result."""
    connector = GitHubConnector(token="")

    with respx.mock:
        respx.get("https://api.github.com/users/nonexistent").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )

        result = await connector.fetch("https://github.com/nonexistent")

    assert result["alive"] is False
    assert result["metrics"]["reputation_score"] == 0
    assert result["metrics"]["activity_score"] == 0


@pytest.mark.asyncio
async def test_github_connector_bad_url():
    """GitHub with unparseable URL returns dead result."""
    connector = GitHubConnector(token="")
    result = await connector.fetch("https://example.com/not-github")
    assert result["alive"] is False


# ── ugig Connector Tests ──

@pytest.mark.asyncio
async def test_ugig_connector_success():
    """ugig connector returns proper metrics."""
    connector = UgigConnector()

    with respx.mock:
        respx.get("https://ugig.net/api/users/gendolf").mock(
            return_value=httpx.Response(200, json={
                "profile": {
                    "id": "123",
                    "username": "gendolf",
                    "average_rating": 4.8,
                    "total_reviews": 12,
                    "skills": ["python", "ai", "automation"],
                    "profile_completed": True,
                    "avatar_url": "https://ugig.net/avatar.jpg",
                    "created_at": "2024-06-01T00:00:00Z",
                    "updated_at": "2026-02-20T00:00:00Z",
                }
            })
        )
        respx.get("https://ugig.net/api/reviews").mock(
            return_value=httpx.Response(200, json={
                "data": [
                    {"rating": 5, "text": "Great work"},
                    {"rating": 4, "text": "Good"},
                ]
            })
        )

        result = await connector.fetch("https://ugig.net/user/gendolf")

    assert result["alive"] is True
    assert result["platform"] == "ugig"
    assert result["metrics"]["reputation_score"] > 0
    assert result["metrics"]["verification_level"] == "verified"
    assert result["metrics"]["evidence_count"] > 0


@pytest.mark.asyncio
async def test_ugig_connector_no_reviews():
    """ugig with no reviews = reputation 0."""
    connector = UgigConnector()

    with respx.mock:
        respx.get("https://ugig.net/api/users/newagent").mock(
            return_value=httpx.Response(200, json={
                "profile": {
                    "id": "456",
                    "username": "newagent",
                    "average_rating": 0,
                    "total_reviews": 0,
                    "skills": [],
                    "profile_completed": False,
                    "created_at": "2026-02-01T00:00:00Z",
                    "updated_at": "2026-02-01T00:00:00Z",
                }
            })
        )
        respx.get("https://ugig.net/api/reviews").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        result = await connector.fetch("https://ugig.net/user/newagent")

    assert result["alive"] is True
    assert result["metrics"]["reputation_score"] == 0  # HONEST


@pytest.mark.asyncio
async def test_ugig_connector_bad_url():
    connector = UgigConnector()
    result = await connector.fetch("https://example.com/not-ugig")
    assert result["alive"] is False


# ── Generic Connector Tests ──

@pytest.mark.asyncio
async def test_generic_connector_alive():
    """Generic connector checks HTTP liveness."""
    connector = GenericConnector()

    with respx.mock:
        respx.get("https://example.com/agent").mock(
            return_value=httpx.Response(200, text="<html><title>Agent</title></html>",
                                        headers={"content-type": "text/html"})
        )

        result = await connector.fetch("https://example.com/agent")

    assert result["alive"] is True
    assert result["platform"] == "generic"
    assert result["metrics"]["activity_score"] >= 10
    # Generic = low reputation, HONEST
    assert result["metrics"]["reputation_score"] == 0


@pytest.mark.asyncio
async def test_generic_connector_dead():
    """Generic connector handles connection errors."""
    connector = GenericConnector()

    with respx.mock:
        respx.get("https://dead-site.example.com").mock(side_effect=httpx.ConnectError("refused"))

        result = await connector.fetch("https://dead-site.example.com")

    assert result["alive"] is False
    assert result["metrics"]["activity_score"] == 0
    assert result["metrics"]["reputation_score"] == 0
