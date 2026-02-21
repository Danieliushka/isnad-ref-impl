"""Comprehensive tests for isnad CLI module."""

import json
import os
import sys
import tempfile
import pytest

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from isnad.core import AgentIdentity, Attestation, TrustChain
from isnad.cli import main, build_parser


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temp directory."""
    return tmp_path


@pytest.fixture
def alice(tmp_dir):
    """Create and save Alice's identity."""
    identity = AgentIdentity()
    path = str(tmp_dir / "alice.json")
    identity.save(path)
    return identity, path


@pytest.fixture
def bob(tmp_dir):
    """Create and save Bob's identity."""
    identity = AgentIdentity()
    path = str(tmp_dir / "bob.json")
    identity.save(path)
    return identity, path


@pytest.fixture
def charlie(tmp_dir):
    identity = AgentIdentity()
    path = str(tmp_dir / "charlie.json")
    identity.save(path)
    return identity, path


@pytest.fixture
def sample_chain(tmp_dir, alice, bob, charlie):
    """Create a chain file with some attestations."""
    a_id, _ = alice
    b_id, _ = bob
    c_id, _ = charlie

    att1 = Attestation(subject=b_id.agent_id, witness=a_id.agent_id,
                       task="code-review", evidence="https://example.com/pr/1")
    att1.sign(a_id)

    att2 = Attestation(subject=c_id.agent_id, witness=b_id.agent_id,
                       task="data-analysis")
    att2.sign(b_id)

    att3 = Attestation(subject=c_id.agent_id, witness=a_id.agent_id,
                       task="code-review", evidence="https://example.com/pr/2")
    att3.sign(a_id)

    chain = TrustChain()
    for att in [att1, att2, att3]:
        chain.add(att)

    chain_path = str(tmp_dir / "chain.json")
    chain.save(chain_path)
    return chain_path, chain, [att1, att2, att3]


# ─── Parser tests ──────────────────────────────────────────────────

class TestParser:
    def test_build_parser(self):
        parser = build_parser()
        assert parser is not None

    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            main([])

    def test_json_flag_parsed(self):
        parser = build_parser()
        args = parser.parse_args(["--json", "score", "agent1", "-c", "chain.json"])
        assert args.json is True
        assert args.command == "score"


# ─── Attest command ────────────────────────────────────────────────

class TestAttest:
    def test_attest_creates_attestation(self, alice, tmp_dir, capsys):
        a_id, a_path = alice
        out = str(tmp_dir / "att.json")
        result = main(["attest", "subject-agent", "code-review",
                       "-k", a_path, "-o", out])
        assert result is not None
        assert result["witness"] == a_id.agent_id
        assert result["subject"] == "subject-agent"
        assert result["task"] == "code-review"
        assert os.path.exists(out)

        with open(out) as f:
            saved = json.load(f)
        assert saved["attestation_id"] == result["attestation_id"]

    def test_attest_json_output(self, alice, capsys):
        _, a_path = alice
        main(["--json", "attest", "subj", "task1", "-k", a_path])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "attestation_id" in data

    def test_attest_human_output(self, alice, capsys):
        _, a_path = alice
        main(["attest", "subj", "task1", "-k", a_path])
        captured = capsys.readouterr()
        assert "✅ Attestation created" in captured.out

    def test_attest_with_evidence(self, alice, capsys):
        _, a_path = alice
        result = main(["--json", "attest", "subj", "task1",
                       "-k", a_path, "-e", "https://evidence.example.com"])
        assert result["evidence"] == "https://evidence.example.com"

    def test_attest_signature_valid(self, alice):
        _, a_path = alice
        result = main(["--json", "attest", "subj", "task1", "-k", a_path])
        att = Attestation.from_dict(result)
        assert att.verify()


# ─── Verify command ────────────────────────────────────────────────

class TestVerify:
    def test_verify_valid(self, alice, tmp_dir, capsys):
        a_id, a_path = alice
        att = Attestation(subject="subj", witness=a_id.agent_id, task="test")
        att.sign(a_id)
        att_file = str(tmp_dir / "att.json")
        with open(att_file, 'w') as f:
            json.dump(att.to_dict(), f)

        result = main(["--json", "verify", att_file])
        assert result["valid"] is True
        assert result["signature_valid"] is True

    def test_verify_invalid_signature(self, tmp_dir, capsys):
        att_file = str(tmp_dir / "bad.json")
        with open(att_file, 'w') as f:
            json.dump({
                "subject": "s", "witness": "w", "task": "t",
                "signature": "deadbeef", "witness_pubkey": "00" * 32,
                "evidence": "", "timestamp": "2024-01-01T00:00:00"
            }, f)

        result = main(["--json", "verify", att_file])
        assert result["valid"] is False

    def test_verify_human_output_valid(self, alice, tmp_dir, capsys):
        a_id, a_path = alice
        att = Attestation(subject="subj", witness=a_id.agent_id, task="test")
        att.sign(a_id)
        att_file = str(tmp_dir / "att.json")
        with open(att_file, 'w') as f:
            json.dump(att.to_dict(), f)

        main(["verify", att_file])
        captured = capsys.readouterr()
        assert "✅ VALID" in captured.out

    def test_verify_with_revocation_list(self, alice, tmp_dir):
        a_id, _ = alice
        att = Attestation(subject="subj", witness=a_id.agent_id, task="test")
        att.sign(a_id)

        att_file = str(tmp_dir / "att.json")
        with open(att_file, 'w') as f:
            json.dump(att.to_dict(), f)

        # Create revocation list with this attestation revoked
        from isnad.revocation import RevocationList, RevocationReason
        rl = RevocationList()
        rl.revoke(att.attestation_id, reason=RevocationReason.KEY_COMPROMISE)
        rl_file = str(tmp_dir / "revocations.json")
        with open(rl_file, 'w') as f:
            f.write(rl.to_json())

        result = main(["--json", "verify", att_file, "-r", rl_file])
        assert result["valid"] is False
        assert result["revoked"] is True

    def test_verify_from_stdin(self, alice, tmp_dir, monkeypatch):
        a_id, _ = alice
        att = Attestation(subject="subj", witness=a_id.agent_id, task="test")
        att.sign(a_id)

        import io
        monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(att.to_dict())))
        result = main(["--json", "verify", "-"])
        assert result["valid"] is True


# ─── Chain command ─────────────────────────────────────────────────

class TestChain:
    def test_chain_show(self, sample_chain, bob):
        chain_path, chain, atts = sample_chain
        b_id, _ = bob
        result = main(["--json", "chain", b_id.agent_id, "-c", chain_path])
        assert result["attestation_count"] == 1
        assert result["attestations"][0]["task"] == "code-review"

    def test_chain_multiple_attestations(self, sample_chain, charlie):
        chain_path, _, _ = sample_chain
        c_id, _ = charlie
        result = main(["--json", "chain", c_id.agent_id, "-c", chain_path])
        assert result["attestation_count"] == 2

    def test_chain_transitive_trust(self, sample_chain, alice, charlie):
        chain_path, _, _ = sample_chain
        a_id, _ = alice
        c_id, _ = charlie
        result = main(["--json", "chain", c_id.agent_id, "-c", chain_path,
                       "-f", a_id.agent_id])
        assert "transitive_trust" in result
        assert result["transitive_trust"] > 0

    def test_chain_human_output(self, sample_chain, bob, capsys):
        chain_path, _, _ = sample_chain
        b_id, _ = bob
        main(["chain", b_id.agent_id, "-c", chain_path])
        captured = capsys.readouterr()
        assert "🔗 Trust chain" in captured.out

    def test_chain_unknown_agent(self, sample_chain):
        chain_path, _, _ = sample_chain
        result = main(["--json", "chain", "unknown-agent", "-c", chain_path])
        assert result["attestation_count"] == 0


# ─── Score command ─────────────────────────────────────────────────

class TestScore:
    def test_score_basic(self, sample_chain, bob):
        chain_path, _, _ = sample_chain
        b_id, _ = bob
        result = main(["--json", "score", b_id.agent_id, "-c", chain_path])
        assert result["trust_score"] > 0
        assert result["attestation_count"] == 1

    def test_score_with_scope(self, sample_chain, charlie):
        chain_path, _, _ = sample_chain
        c_id, _ = charlie
        result = main(["--json", "score", c_id.agent_id, "-c", chain_path,
                       "-s", "code-review"])
        assert result["scope"] == "code-review"
        assert result["trust_score"] > 0

    def test_score_unknown_agent(self, sample_chain):
        chain_path, _, _ = sample_chain
        result = main(["--json", "score", "unknown", "-c", chain_path])
        assert result["trust_score"] == 0

    def test_score_human_output(self, sample_chain, bob, capsys):
        chain_path, _, _ = sample_chain
        b_id, _ = bob
        main(["score", b_id.agent_id, "-c", chain_path])
        captured = capsys.readouterr()
        assert "📊 Trust Score" in captured.out


# ─── Revoke command ────────────────────────────────────────────────

class TestRevoke:
    def test_revoke_creates_record(self, tmp_dir, capsys):
        out = str(tmp_dir / "revocations.json")
        result = main(["--json", "revoke", "test-att-id",
                       "--reason", "key_compromise",
                       "--revoked-by", "admin",
                       "-o", out])
        assert result["attestation_id"] == "test-att-id"
        assert result["reason"] == "key_compromise"
        assert os.path.exists(out)

    def test_revoke_appends_to_list(self, tmp_dir):
        rl_file = str(tmp_dir / "rl.json")
        main(["--json", "revoke", "att-1", "--reason", "superseded", "-o", rl_file])
        main(["--json", "revoke", "att-2", "--reason", "superseded",
              "-r", rl_file, "-o", rl_file])

        with open(rl_file) as f:
            data = json.load(f)
        assert len(data) == 2

    def test_revoke_human_output(self, tmp_dir, capsys):
        main(["revoke", "att-id", "--reason", "superseded"])
        captured = capsys.readouterr()
        assert "🚫 Attestation revoked" in captured.out

    def test_revoke_all_reasons(self, tmp_dir):
        for reason in ["key_compromise", "superseded", "ceased_operation", "privilege_withdrawn"]:
            result = main(["--json", "revoke", f"att-{reason}", "--reason", reason])
            assert result["reason"] == reason


# ─── Delegate command ──────────────────────────────────────────────

class TestDelegate:
    def test_delegate_create(self, alice, bob, tmp_dir):
        a_id, a_path = alice
        b_id, _ = bob
        reg_file = str(tmp_dir / "registry.json")

        result = main(["--json", "delegate", "create", b_id.public_key_hex,
                       "-k", a_path, "-s", "code-review", "-r", reg_file])
        assert result["delegator_key_hex"] == a_id.public_key_hex
        assert result["delegate_key_hex"] == b_id.public_key_hex
        assert os.path.exists(reg_file)

    def test_delegate_verify(self, alice, bob, tmp_dir):
        a_id, a_path = alice
        b_id, _ = bob
        reg_file = str(tmp_dir / "registry.json")

        result = main(["--json", "delegate", "create", b_id.public_key_hex,
                       "-k", a_path, "-r", reg_file])
        d_hash = result["content_hash"]

        result2 = main(["--json", "delegate", "verify", d_hash, "-r", reg_file])
        assert result2["valid"] is True

    def test_delegate_list(self, alice, bob, tmp_dir):
        a_id, a_path = alice
        b_id, _ = bob
        reg_file = str(tmp_dir / "registry.json")

        main(["--json", "delegate", "create", b_id.public_key_hex,
              "-k", a_path, "-s", "code-review", "-r", reg_file])
        main(["--json", "delegate", "create", b_id.public_key_hex,
              "-k", a_path, "-s", "data-analysis", "-r", reg_file])

        result = main(["--json", "delegate", "list", b_id.public_key_hex,
                       "-r", reg_file])
        assert len(result["delegations"]) == 2

    def test_delegate_list_with_scope(self, alice, bob, tmp_dir):
        a_id, a_path = alice
        b_id, _ = bob
        reg_file = str(tmp_dir / "registry.json")

        main(["--json", "delegate", "create", b_id.public_key_hex,
              "-k", a_path, "-s", "code-review", "-r", reg_file])
        main(["--json", "delegate", "create", b_id.public_key_hex,
              "-k", a_path, "-s", "data-analysis", "-r", reg_file])

        result = main(["--json", "delegate", "list", b_id.public_key_hex,
                       "-r", reg_file, "-s", "code-review"])
        assert len(result["delegations"]) == 1

    def test_delegate_human_output(self, alice, bob, tmp_dir, capsys):
        _, a_path = alice
        b_id, _ = bob
        main(["delegate", "create", b_id.public_key_hex, "-k", a_path])
        captured = capsys.readouterr()
        assert "✅ Delegation created" in captured.out


# ─── Stats command ─────────────────────────────────────────────────

class TestStats:
    def test_stats_basic(self, sample_chain):
        chain_path, _, _ = sample_chain
        result = main(["--json", "stats", "-c", chain_path])
        assert result["network"]["agents"] == 3
        assert result["network"]["edges"] == 3

    def test_stats_top_agents(self, sample_chain):
        chain_path, _, _ = sample_chain
        result = main(["--json", "stats", "-c", chain_path, "-t", "2"])
        assert len(result["top_agents"]) <= 2

    def test_stats_communities(self, sample_chain):
        chain_path, _, _ = sample_chain
        result = main(["--json", "stats", "-c", chain_path])
        assert len(result["communities"]) >= 1

    def test_stats_human_output(self, sample_chain, capsys):
        chain_path, _, _ = sample_chain
        main(["stats", "-c", chain_path])
        captured = capsys.readouterr()
        assert "📊 Network Statistics" in captured.out

    def test_stats_empty_chain(self, tmp_dir):
        chain_path = str(tmp_dir / "empty.json")
        with open(chain_path, 'w') as f:
            json.dump([], f)
        result = main(["--json", "stats", "-c", chain_path])
        assert result["network"]["agents"] == 0


# ─── Integration tests ────────────────────────────────────────────

class TestIntegration:
    def test_full_workflow(self, alice, bob, tmp_dir):
        """Full workflow: attest → verify → score → revoke → verify again."""
        a_id, a_path = alice
        b_id, _ = bob

        # Create attestation
        att_file = str(tmp_dir / "att.json")
        att_result = main(["--json", "attest", b_id.agent_id, "code-review",
                          "-k", a_path, "-o", att_file])

        # Verify it
        verify_result = main(["--json", "verify", att_file])
        assert verify_result["valid"] is True

        # Build chain and check score
        chain_path = str(tmp_dir / "chain.json")
        chain = TrustChain()
        att = Attestation.from_dict(att_result)
        chain.add(att)
        chain.save(chain_path)

        score_result = main(["--json", "score", b_id.agent_id, "-c", chain_path])
        assert score_result["trust_score"] > 0

        # Revoke
        rl_file = str(tmp_dir / "rl.json")
        main(["--json", "revoke", att_result["attestation_id"],
              "--reason", "key_compromise", "-o", rl_file])

        # Verify again with revocation list
        verify2 = main(["--json", "verify", att_file, "-r", rl_file])
        assert verify2["valid"] is False
        assert verify2["revoked"] is True

    def test_python_m_isnad(self):
        """Test that python -m isnad works (just help)."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "isnad", "--help"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), '..', 'src')
        )
        assert result.returncode == 0
        assert "isnad" in result.stdout
