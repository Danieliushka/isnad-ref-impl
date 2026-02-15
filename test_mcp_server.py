"""Tests for isnad MCP Server."""

import json
import unittest
from mcp_server import MCPHandler
from isnad import AgentIdentity, Attestation, TrustChain


class TestMCPTools(unittest.TestCase):

    def setUp(self):
        self.handler = MCPHandler.__new__(MCPHandler)
        MCPHandler.trust_chain = TrustChain()

    def test_list_tools_returns_5_tools(self):
        result = self.handler._list_tools({})
        self.assertEqual(len(result["tools"]), 5)
        names = {t["name"] for t in result["tools"]}
        self.assertEqual(names, {"isnad_keygen", "isnad_attest", "isnad_verify", "isnad_score", "isnad_chain_trust"})

    def test_each_tool_has_schema(self):
        result = self.handler._list_tools({})
        for tool in result["tools"]:
            self.assertIn("inputSchema", tool)
            self.assertIn("description", tool)

    def test_keygen_returns_keypair(self):
        result = self.handler._keygen({})
        self.assertIn("public_key", result)
        self.assertIn("private_key", result)
        self.assertEqual(result["algorithm"], "Ed25519")
        self.assertEqual(len(result["public_key"]), 64)

    def test_attest_and_verify_roundtrip(self):
        kp = self.handler._keygen({})
        subject_kp = self.handler._keygen({})
        
        att_dict = self.handler._attest({
            "witness_private_key": kp["private_key"],
            "subject_id": subject_kp["agent_id"],
            "task": "code-review",
            "outcome": "success",
            "confidence": 0.9,
        })
        self.assertIn("signature", att_dict)

        verify_result = self.handler._verify({"attestation": att_dict})
        self.assertTrue(verify_result["valid"])

    def test_verify_fails_with_tampered_attestation(self):
        kp = self.handler._keygen({})
        att_dict = self.handler._attest({
            "witness_private_key": kp["private_key"],
            "subject_id": "target-agent",
            "task": "deploy",
            "outcome": "success",
        })
        att_dict["task"] = "tampered"
        verify_result = self.handler._verify({"attestation": att_dict})
        self.assertFalse(verify_result["valid"])

    def test_call_tool_unknown(self):
        result = self.handler._call_tool({"name": "nonexistent", "arguments": {}})
        self.assertIn("error", result)

    def test_call_tool_keygen(self):
        result = self.handler._call_tool({
            "name": "isnad_keygen",
            "arguments": {},
        })
        self.assertIn("content", result)
        data = json.loads(result["content"][0]["text"])
        self.assertIn("public_key", data)

    def test_score_with_attestations(self):
        kp = self.handler._keygen({})
        subject_kp = self.handler._keygen({})
        
        self.handler._attest({
            "witness_private_key": kp["private_key"],
            "subject_id": subject_kp["agent_id"],
            "task": "analysis",
            "outcome": "success",
            "confidence": 0.8,
        })
        
        result = self.handler._score({"agent_id": subject_kp["agent_id"]})
        self.assertIn("score", result)
        self.assertGreater(result["score"], 0)

    def test_chain_trust(self):
        kp1 = self.handler._keygen({})
        kp2 = self.handler._keygen({})
        kp3 = self.handler._keygen({})
        
        # kp1 attests kp2
        self.handler._attest({
            "witness_private_key": kp1["private_key"],
            "subject_id": kp2["agent_id"],
            "task": "delegation",
            "outcome": "success",
        })
        # kp2 attests kp3
        self.handler._attest({
            "witness_private_key": kp2["private_key"],
            "subject_id": kp3["agent_id"],
            "task": "delegation",
            "outcome": "success",
        })
        
        result = self.handler._chain_trust({
            "source": kp1["agent_id"],
            "target": kp3["agent_id"],
        })
        self.assertIn("trust", result)

    def test_full_mcp_flow(self):
        """End-to-end: keygen → attest → verify → score via call_tool."""
        # Generate two identities
        r1 = self.handler._call_tool({"name": "isnad_keygen", "arguments": {}})
        r2 = self.handler._call_tool({"name": "isnad_keygen", "arguments": {}})
        id1 = json.loads(r1["content"][0]["text"])
        id2 = json.loads(r2["content"][0]["text"])
        
        # id1 attests id2
        r3 = self.handler._call_tool({"name": "isnad_attest", "arguments": {
            "witness_private_key": id1["private_key"],
            "subject_id": id2["agent_id"],
            "task": "research",
            "outcome": "success",
            "confidence": 0.95,
        }})
        att = json.loads(r3["content"][0]["text"])
        
        # Verify
        r4 = self.handler._call_tool({"name": "isnad_verify", "arguments": {
            "attestation": att,
        }})
        verify = json.loads(r4["content"][0]["text"])
        self.assertTrue(verify["valid"])
        
        # Score
        r5 = self.handler._call_tool({"name": "isnad_score", "arguments": {
            "agent_id": id2["agent_id"],
        }})
        score = json.loads(r5["content"][0]["text"])
        self.assertGreater(score["score"], 0)


if __name__ == "__main__":
    unittest.main()
