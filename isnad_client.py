"""
isnad-client — Python SDK for interacting with the isnad Sandbox API.

Usage:
    from isnad_client import IsnadClient

    client = IsnadClient("http://localhost:8420")
    me = client.generate_keys()
    att = client.create_attestation(witness_id=me["agent_id"], subject_id="other-agent", task="code-review")
    score = client.trust_score(me["agent_id"])
"""

from __future__ import annotations

import httpx
from dataclasses import dataclass, field
from typing import Optional


class IsnadError(Exception):
    """Raised when the sandbox API returns an error."""
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"[{status}] {detail}")


@dataclass
class IsnadClient:
    """Lightweight client for the isnad Sandbox API."""

    base_url: str = "http://localhost:8420"
    timeout: float = 10.0
    _http: httpx.Client = field(init=False, repr=False)

    def __post_init__(self):
        self._http = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- internal --

    def _request(self, method: str, path: str, **kwargs) -> dict:
        r = self._http.request(method, path, **kwargs)
        if r.status_code >= 400:
            detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            raise IsnadError(r.status_code, detail)
        return r.json()

    # -- Keys --

    def generate_keys(self) -> dict:
        """Generate a new Ed25519 keypair. Returns {agent_id, keys: {public, private}}."""
        return self._request("POST", "/sandbox/keys/generate")

    # -- Attestations --

    def create_attestation(self, witness_id: str, subject_id: str, task: str, evidence: str = "") -> dict:
        """Create and sign an attestation. Witness must have generated keys first."""
        return self._request("POST", "/sandbox/attestations/create", json={
            "witness_id": witness_id,
            "subject_id": subject_id,
            "task": task,
            "evidence": evidence,
        })

    def verify_attestation(self, attestation: dict) -> dict:
        """Verify an attestation dict (must contain subject, witness, task, evidence, timestamp, signature, witness_pubkey)."""
        return self._request("POST", "/sandbox/attestations/verify", json=attestation)

    def batch_verify(self, attestations: list[dict]) -> dict:
        """Verify multiple attestations in one call."""
        return self._request("POST", "/sandbox/attestations/batch-verify", json={"attestations": attestations})

    # -- Chain & Trust --

    def get_chain(self, agent_id: str) -> dict:
        """Get attestation chain for an agent."""
        return self._request("GET", f"/sandbox/chain/{agent_id}")

    def trust_score(self, agent_id: str, scope: Optional[str] = None) -> dict:
        """Calculate TrustScore for an agent."""
        return self._request("POST", "/sandbox/trust/score", json={"agent_id": agent_id, "scope": scope})

    def reputation(self, agent_id: str) -> dict:
        """Full reputation summary: score, peers, task distribution."""
        return self._request("GET", f"/sandbox/agent/{agent_id}/reputation")

    # -- Webhooks --

    def subscribe_webhook(self, url: str, events: list[str] | None = None, filter_issuer: str | None = None, filter_subject: str | None = None) -> dict:
        """Subscribe a URL to sandbox events."""
        payload: dict = {"url": url}
        if events:
            payload["events"] = events
        if filter_issuer:
            payload["filter_issuer"] = filter_issuer
        if filter_subject:
            payload["filter_subject"] = filter_subject
        return self._request("POST", "/sandbox/webhooks/subscribe", json=payload)

    def list_webhooks(self) -> dict:
        """List active webhook subscriptions."""
        return self._request("GET", "/sandbox/webhooks")

    # -- Health --

    def health(self) -> dict:
        return self._request("GET", "/sandbox/health")

    # -- Convenience: cross-agent verification flow --

    def cross_verify(self, agent_a: str, agent_b: str, task: str = "cross-verification") -> dict:
        """
        Run a mutual attestation between two agents.
        Both must have generated keys first.
        Returns both attestations and resulting trust scores.
        """
        att_a = self.create_attestation(witness_id=agent_a, subject_id=agent_b, task=task, evidence=f"cross-verify by {agent_a}")
        att_b = self.create_attestation(witness_id=agent_b, subject_id=agent_a, task=task, evidence=f"cross-verify by {agent_b}")
        score_a = self.trust_score(agent_a)
        score_b = self.trust_score(agent_b)
        return {
            "attestation_a_to_b": att_a["attestation"],
            "attestation_b_to_a": att_b["attestation"],
            "score_a": score_a["trust_score"],
            "score_b": score_b["trust_score"],
        }


# --- CLI demo ---

if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8420"
    print(f"🔗 Connecting to isnad sandbox at {url}")

    with IsnadClient(url) as c:
        print(f"✅ Health: {c.health()}")

        # Generate two agents
        alice = c.generate_keys()
        bob = c.generate_keys()
        print(f"🔑 Alice: {alice['agent_id'][:12]}...")
        print(f"🔑 Bob:   {bob['agent_id'][:12]}...")

        # Cross-verify
        result = c.cross_verify(alice["agent_id"], bob["agent_id"], task="sdk-test")
        print(f"✅ Cross-verify complete!")
        print(f"   Alice score: {result['score_a']}")
        print(f"   Bob score:   {result['score_b']}")

        # Check reputation
        rep = c.reputation(alice["agent_id"])
        print(f"📊 Alice reputation: {rep['trust_score']} ({rep['attestations_received']} received, {rep['attestations_given']} given)")
