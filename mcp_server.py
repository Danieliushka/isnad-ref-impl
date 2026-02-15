"""
isnad MCP Server — Model Context Protocol integration for Agent Trust Protocol.

Exposes isnad trust verification as MCP tools that any LLM/agent framework can call.
Compatible with Claude, ChatGPT, Cursor, and any MCP-compliant client.

Usage:
    python mcp_server.py [--port 8080]
"""

import json
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from isnad import AgentIdentity, Attestation, TrustChain


class MCPHandler(BaseHTTPRequestHandler):
    """MCP-compatible HTTP handler for isnad trust operations."""

    trust_chain = TrustChain()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        routes = {
            "/mcp/tools": self._list_tools,
            "/mcp/call": self._call_tool,
        }

        handler = routes.get(self.path)
        if handler:
            result = handler(body)
            self._respond(200, result)
        else:
            self._respond(404, {"error": f"Unknown endpoint: {self.path}"})

    def do_GET(self):
        if self.path == "/mcp/tools":
            self._respond(200, self._list_tools({}))
        elif self.path == "/health":
            self._respond(200, {"status": "ok", "protocol": "isnad-mcp", "version": "0.1.0"})
        else:
            self._respond(404, {"error": "Not found"})

    def _list_tools(self, _body):
        return {
            "tools": [
                {
                    "name": "isnad_keygen",
                    "description": "Generate an Ed25519 keypair for agent identity. Returns agent_id, public_key, private_key.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    },
                },
                {
                    "name": "isnad_attest",
                    "description": "Create a signed attestation (witness vouches for subject on a task). Returns attestation dict with signature.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "witness_private_key": {"type": "string", "description": "Hex-encoded private key of witness"},
                            "subject_id": {"type": "string", "description": "Agent ID being attested (public key hex)"},
                            "task": {"type": "string", "description": "Task/capability being attested"},
                            "outcome": {"type": "string", "enum": ["success", "failure", "partial"], "description": "Outcome of the task"},
                            "confidence": {"type": "number", "description": "Confidence level 0.0-1.0"},
                        },
                        "required": ["witness_private_key", "subject_id", "task", "outcome"],
                    },
                },
                {
                    "name": "isnad_verify",
                    "description": "Verify an attestation's cryptographic signature.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "attestation": {"type": "object", "description": "Full attestation dict to verify"},
                        },
                        "required": ["attestation"],
                    },
                },
                {
                    "name": "isnad_score",
                    "description": "Calculate trust score for an agent. Returns score 0.0-1.0.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "agent_id": {"type": "string", "description": "Agent public key hex to score"},
                            "scope": {"type": "string", "description": "Optional task scope filter"},
                        },
                        "required": ["agent_id"],
                    },
                },
                {
                    "name": "isnad_chain_trust",
                    "description": "Calculate transitive trust between two agents through the attestation graph.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "description": "Source agent ID"},
                            "target": {"type": "string", "description": "Target agent ID"},
                            "max_hops": {"type": "integer", "description": "Max chain length (default 5)"},
                        },
                        "required": ["source", "target"],
                    },
                },
            ]
        }

    def _call_tool(self, body):
        tool_name = body.get("name", "")
        args = body.get("arguments", {})

        handlers = {
            "isnad_keygen": self._keygen,
            "isnad_attest": self._attest,
            "isnad_verify": self._verify,
            "isnad_score": self._score,
            "isnad_chain_trust": self._chain_trust,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            result = handler(args)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e), "isError": True}

    @staticmethod
    def _keygen(_args):
        identity = AgentIdentity()
        keys = identity.export_keys()
        return {
            "agent_id": identity.agent_id,
            "public_key": keys["public_key"],
            "private_key": keys["private_key"],
            "algorithm": "Ed25519",
        }

    def _attest(self, args):
        witness = AgentIdentity.from_private_key(args["witness_private_key"])
        evidence = args.get("outcome", "success")
        if args.get("confidence"):
            evidence += f" (confidence: {args['confidence']})"
        att = Attestation(
            subject=args["subject_id"],
            witness=witness.agent_id,
            task=args["task"],
            evidence=evidence,
        )
        att.sign(witness)
        self.trust_chain.add(att)
        return att.to_dict()

    @staticmethod
    def _verify(args):
        att = Attestation.from_dict(args["attestation"])
        valid = att.verify()
        return {"valid": valid, "attestation_id": att.attestation_id}

    def _score(self, args):
        score = self.trust_chain.trust_score(
            agent_id=args["agent_id"],
            scope=args.get("scope"),
        )
        return {"agent_id": args["agent_id"], "score": score, "scope": args.get("scope")}

    def _chain_trust(self, args):
        trust = self.trust_chain.chain_trust(
            source=args["source"],
            target=args["target"],
            max_hops=args.get("max_hops", 5),
        )
        return {"source": args["source"], "target": args["target"], "trust": trust}

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="isnad MCP Server")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), MCPHandler)
    print(f"🔐 isnad MCP Server running on port {args.port}")
    print(f"   Tools: /mcp/tools | Call: /mcp/call | Health: /health")
    server.serve_forever()


if __name__ == "__main__":
    main()
