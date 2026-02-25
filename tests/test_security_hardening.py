"""
Security hardening tests for isnad API v1 endpoints.

Tests: SQL injection, XSS, oversized payloads, invalid API keys,
error response safety, security headers, admin auth.
"""

import os
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-hardening")

import pytest
from fastapi.testclient import TestClient
from isnad.api_v1 import create_app

app = create_app(allowed_origins=["*"], use_lifespan=False)
client = TestClient(app)


class TestSQLInjection:
    def test_check_endpoint_sqli(self):
        payloads = [
            "'; DROP TABLE agents; --",
            "1 UNION SELECT * FROM agents",
            "1; DELETE FROM agents WHERE 1=1",
        ]
        for payload in payloads:
            resp = client.get(f"/api/v1/check/{payload}")
            assert resp.status_code in (400, 404, 422, 500), f"SQLi not blocked: {payload}"

    def test_explorer_search_sqli(self):
        resp = client.get("/api/v1/explorer", params={"search": "'; DROP TABLE agents;--"})
        assert resp.status_code in (200, 400, 500)


class TestXSS:
    def test_register_xss_name(self):
        resp = client.post("/api/v1/agents/register", json={
            "name": "<script>alert('xss')</script>",
            "description": "test agent",
        })
        assert resp.status_code in (400, 503)

    def test_register_xss_description(self):
        resp = client.post("/api/v1/agents/register", json={
            "name": "safe-agent",
            "description": '<img onerror="alert(1)" src=x>',
        })
        assert resp.status_code in (400, 503)

    def test_register_xss_javascript_uri(self):
        resp = client.post("/api/v1/agents/register", json={
            "name": "safe-agent",
            "description": "javascript:alert(document.cookie)",
        })
        assert resp.status_code in (400, 503)


class TestOversizedPayloads:
    def test_large_body_rejected(self):
        resp = client.post(
            "/api/v1/agents/register",
            content=b"x" * (2 * 1024 * 1024),
            headers={"content-type": "application/json", "content-length": str(2 * 1024 * 1024)},
        )
        assert resp.status_code == 413

    def test_normal_body_accepted(self):
        resp = client.post("/api/v1/agents/register", json={
            "name": "normal-agent", "description": "A normal description",
        })
        assert resp.status_code != 413


class TestInvalidAPIKeys:
    def test_missing_api_key_patch(self):
        resp = client.patch("/api/v1/agents/some-id", json={"name": "new"})
        assert resp.status_code in (401, 503)  # 503 if no DB, 401 if DB available

    def test_invalid_api_key_patch(self):
        resp = client.patch(
            "/api/v1/agents/some-id", json={"name": "new"},
            headers={"X-API-Key": "fake_key_12345"},
        )
        assert resp.status_code in (403, 404, 500, 503)

    def test_missing_admin_key(self):
        resp = client.post("/api/v1/admin/scan/some-id")
        assert resp.status_code in (401, 403)

    def test_invalid_admin_key(self):
        resp = client.post(
            "/api/v1/admin/scan/some-id",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 403


class TestErrorResponseSafety:
    def test_404_no_stack_trace(self):
        resp = client.get("/api/v1/explorer/nonexistent-agent-xyz")
        body = str(resp.json())
        assert "traceback" not in body.lower()
        assert "File " not in body

    def test_error_no_db_details(self):
        resp = client.get("/api/v1/agents/nonexistent")
        body = str(resp.json())
        assert "postgresql" not in body.lower()
        assert "asyncpg" not in body.lower()


class TestSecurityHeadersV1:
    def test_security_headers_present(self):
        resp = client.get("/api/v1/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert "max-age=" in resp.headers.get("strict-transport-security", "")
