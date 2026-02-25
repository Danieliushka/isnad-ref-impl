"""Generic platform connector — fallback for unknown platforms.

Checks: HTTP alive, SSL cert info, response time, basic page analysis.
"""

from __future__ import annotations

import logging
import ssl
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from .base import BaseConnector, ConnectorResult, ConnectorMetrics

logger = logging.getLogger(__name__)


class GenericConnector(BaseConnector):
    platform_name = "generic"

    async def fetch(self, url: str) -> ConnectorResult:
        raw_data: dict = {}
        alive = False
        response_time_ms = 0.0

        # HTTP check
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url)
                alive = resp.status_code < 500
                response_time_ms = resp.elapsed.total_seconds() * 1000
                raw_data["status_code"] = resp.status_code
                raw_data["response_time_ms"] = round(response_time_ms, 1)
                raw_data["content_length"] = len(resp.content)
                raw_data["content_type"] = resp.headers.get("content-type", "")

                # Basic page analysis
                text = resp.text[:5000] if resp.text else ""
                raw_data["has_title"] = "<title" in text.lower()
                raw_data["has_meta_description"] = 'name="description"' in text.lower()

        except httpx.HTTPError as e:
            logger.warning("Generic fetch failed for %s: %s", url, e)
            return self._dead_result(url, str(e))

        # SSL cert info
        ssl_info = self._get_ssl_info(url)
        if ssl_info:
            raw_data["ssl"] = ssl_info

        # Compute minimal metrics — HONEST: generic = low scores
        activity_score = 10 if alive else 0  # Alive is minimal evidence
        reputation_score = 0  # No reputation data from generic check
        longevity_days = 0

        # SSL adds slight verification
        verification = "none"
        if ssl_info and ssl_info.get("valid"):
            verification = "basic"
            if ssl_info.get("days_remaining", 0) > 30:
                activity_score = min(activity_score + 5, 100)

        evidence_count = 1 if alive else 0
        if ssl_info and ssl_info.get("valid"):
            evidence_count += 1

        return ConnectorResult(
            platform="generic",
            url=url,
            alive=alive,
            raw_data=raw_data,
            metrics=ConnectorMetrics(
                activity_score=activity_score,
                reputation_score=reputation_score,
                longevity_days=longevity_days,
                verification_level=verification,
                evidence_count=evidence_count,
            ),
        )

    def _get_ssl_info(self, url: str) -> dict | None:
        """Get SSL certificate info for the URL's host."""
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return None

        hostname = parsed.hostname
        port = parsed.port or 443
        if not hostname:
            return None

        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    if not cert:
                        return {"valid": False}

                    # Parse expiry
                    not_after = cert.get("notAfter", "")
                    not_before = cert.get("notBefore", "")
                    issuer = dict(x[0] for x in cert.get("issuer", ()))

                    days_remaining = 0
                    if not_after:
                        try:
                            expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                            expiry = expiry.replace(tzinfo=timezone.utc)
                            days_remaining = (expiry - datetime.now(timezone.utc)).days
                        except Exception:
                            pass

                    return {
                        "valid": True,
                        "issuer": issuer.get("organizationName", ""),
                        "not_before": not_before,
                        "not_after": not_after,
                        "days_remaining": days_remaining,
                    }
        except Exception as e:
            logger.debug("SSL check failed for %s: %s", hostname, e)
            return {"valid": False, "error": str(e)}
