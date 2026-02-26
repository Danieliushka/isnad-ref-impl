"""Tests for isnad_client.py SDK against live sandbox."""
import socket
import pytest
from isnad.client import IsnadClient

BASE = "http://localhost:8420"


def _sandbox_available():
    import urllib.request
    try:
        r = urllib.request.urlopen("http://localhost:8420/sandbox/health", timeout=2)
        return r.status == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _sandbox_available(),
    reason="Requires live sandbox server on localhost:8420 with /sandbox endpoints",
)


@pytest.fixture
def client():
    return IsnadClient(BASE)


@pytest.fixture
def two_agents(client):
    a = client.generate_keys()
    b = client.generate_keys()
    return a, b


def test_health(client):
    r = client.health()
    assert r["status"] == "ok"


def test_generate_keys(client):
    r = client.generate_keys()
    assert "agent_id" in r or "public_key" in r


def test_create_and_verify_attestation(two_agents, client):
    a, b = two_agents
    aid = a.get("agent_id", "test-a")
    bid = b.get("agent_id", "test-b")
    att = client.create_attestation(aid, bid, "test-task")
    assert "attestation" in att or "id" in att
    v = client.verify_attestation(att.get("attestation", att))
    assert isinstance(v, dict)


def test_trust_score(two_agents, client):
    a, b = two_agents
    aid = a.get("agent_id", "test-a")
    bid = b.get("agent_id", "test-b")
    att = client.create_attestation(aid, bid, "scoring-task")
    score = client.trust_score(bid)
    assert isinstance(score, dict)


def test_cross_verify(client):
    client.generate_keys()  # generates keys server-side
    client.generate_keys()
    # use agents that already exist from two_agents or generate fresh
    a = client.generate_keys()
    b = client.generate_keys()
    aid = a.get("agent_id", "cv-a")
    bid = b.get("agent_id", "cv-b")
    r = client.cross_verify(aid, bid, "collab-task")
    assert isinstance(r, dict)


def test_batch_verify(two_agents, client):
    a, b = two_agents
    aid = a.get("agent_id", "test-a")
    bid = b.get("agent_id", "test-b")
    att = client.create_attestation(aid, bid, "batch-task")
    attestation = att.get("attestation", att)
    r = client.batch_verify([attestation])
    assert "results" in r


def test_reputation(two_agents, client):
    a, b = two_agents
    bid = b.get("agent_id", "test-b")
    rep = client.reputation(bid)
    assert isinstance(rep, dict)


def test_webhooks(client):
    sub = client.subscribe_webhook("https://example.com/sdk-test")
    assert "subscription" in sub or "id" in sub
    wh = client.list_webhooks()
    assert isinstance(wh, (dict, list))


def test_chain(two_agents, client):
    a, b = two_agents
    aid = a.get("agent_id", "test-a")
    r = client.get_chain(aid)
    assert isinstance(r, dict)
