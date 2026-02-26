"""Tests for isnad_client SDK."""
import socket
import pytest
from isnad.client import IsnadClient, IsnadError

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
    with IsnadClient(BASE) as c:
        yield c


def test_health(client):
    h = client.health()
    assert h["status"] == "ok"


def test_generate_keys(client):
    result = client.generate_keys()
    assert "agent_id" in result
    assert "public" in result["keys"]
    assert "private" in result["keys"]
    assert result["keys"]["public"]["crv"] == "Ed25519"


def test_create_and_verify_attestation(client):
    alice = client.generate_keys()
    bob = client.generate_keys()
    att = client.create_attestation(
        witness_id=alice["agent_id"],
        subject_id=bob["agent_id"],
        task="test-task",
        evidence="sdk test",
    )
    assert att["added_to_chain"]
    # Verify
    v = client.verify_attestation(att["attestation"])
    assert v["valid"]


def test_batch_verify(client):
    a = client.generate_keys()
    b = client.generate_keys()
    att1 = client.create_attestation(a["agent_id"], b["agent_id"], "t1")
    att2 = client.create_attestation(b["agent_id"], a["agent_id"], "t2")
    result = client.batch_verify([att1["attestation"], att2["attestation"]])
    assert result["total"] == 2
    assert result["valid_count"] == 2


def test_trust_score(client):
    a = client.generate_keys()
    b = client.generate_keys()
    client.create_attestation(a["agent_id"], b["agent_id"], "review")
    score = client.trust_score(b["agent_id"])
    assert score["trust_score"] > 0
    assert score["attestation_count"] == 1


def test_reputation(client):
    a = client.generate_keys()
    b = client.generate_keys()
    client.create_attestation(a["agent_id"], b["agent_id"], "audit")
    rep = client.reputation(b["agent_id"])
    assert rep["attestations_received"] == 1
    assert a["agent_id"] in rep["peers"]["witnesses"]


def test_cross_verify(client):
    a = client.generate_keys()
    b = client.generate_keys()
    result = client.cross_verify(a["agent_id"], b["agent_id"])
    assert result["score_a"] > 0
    assert result["score_b"] > 0


def test_webhooks(client):
    sub = client.subscribe_webhook("http://example.com/hook", events=["attestation.created"])
    assert "subscription" in sub
    wh = client.list_webhooks()
    assert wh["count"] >= 1


def test_chain(client):
    a = client.generate_keys()
    b = client.generate_keys()
    client.create_attestation(a["agent_id"], b["agent_id"], "chain-test")
    chain = client.get_chain(b["agent_id"])
    assert chain["received_count"] == 1


def test_error_handling(client):
    with pytest.raises(IsnadError) as exc_info:
        client.create_attestation("nonexistent", "also-nonexistent", "test")
    assert exc_info.value.status == 404
