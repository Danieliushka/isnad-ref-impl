"use client";

import { Navbar } from "@/components/ui/navbar";
import { Card } from "@/components/ui/card";
import { useState } from "react";

/* ── Types ── */
type Method = "GET" | "POST";

interface Param {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

interface Endpoint {
  method: Method;
  path: string;
  title: string;
  description: string;
  auth: boolean;
  params: Param[];
  curl: string;
  response: string;
}

/* ── Data ── */
const endpoints: Endpoint[] = [
  {
    method: "GET",
    path: "/api/v1/check/{agent_id}",
    title: "Trust Check",
    description:
      "Flagship endpoint — run a full 36-module trust evaluation. Returns overall score, 6 category breakdowns, confidence level, risk flags, and attestation count.",
    auth: false,
    params: [
      { name: "agent_id", type: "string", required: true, description: "Agent ID, name, or public key" },
    ],
    curl: `curl https://api.isnad.dev/api/v1/check/gpt-4-assistant`,
    response: JSON.stringify(
      {
        agent_id: "gpt-4-assistant",
        overall_score: 72,
        confidence: "medium",
        risk_flags: [],
        attestation_count: 3,
        last_checked: "2026-02-23T17:00:00Z",
        categories: [
          { name: "identity", score: 83, modules_passed: 5, modules_total: 6 },
          { name: "attestation", score: 50, modules_passed: 3, modules_total: 6 },
          { name: "behavioral", score: 50, modules_passed: 3, modules_total: 6 },
          { name: "platform", score: 100, modules_passed: 6, modules_total: 6 },
          { name: "transactions", score: 67, modules_passed: 4, modules_total: 6 },
          { name: "security", score: 67, modules_passed: 4, modules_total: 6 },
        ],
        certification_id: "a1b2c3d4e5f6g7h8",
        certified: true,
      },
      null,
      2
    ),
  },
  {
    method: "GET",
    path: "/api/v1/explorer",
    title: "List Agents",
    description: "Paginated list of agents with trust scores. Supports search and sorting.",
    auth: false,
    params: [
      { name: "page", type: "int", required: false, description: "Page number (default: 1)" },
      { name: "limit", type: "int", required: false, description: "Results per page, 1–100 (default: 20)" },
      { name: "search", type: "string", required: false, description: "Filter by agent ID or name" },
      { name: "sort", type: "string", required: false, description: "Sort field: trust_score | name | last_checked" },
    ],
    curl: `curl "https://api.isnad.dev/api/v1/explorer?page=1&limit=5"`,
    response: JSON.stringify(
      {
        agents: [
          { agent_id: "gpt-4-assistant", name: "GPT-4 Assistant", trust_score: 0.92, attestation_count: 12, is_certified: true },
          { agent_id: "claude-3-opus", name: "Claude 3 Opus", trust_score: 0.88, attestation_count: 8, is_certified: true },
        ],
        total: 142,
        page: 1,
        limit: 5,
      },
      null,
      2
    ),
  },
  {
    method: "GET",
    path: "/api/v1/explorer/{agent_id}",
    title: "Agent Detail",
    description: "Detailed view of a single agent including metadata and recent attestations.",
    auth: false,
    params: [
      { name: "agent_id", type: "string", required: true, description: "Agent ID or public key" },
    ],
    curl: `curl https://api.isnad.dev/api/v1/explorer/gpt-4-assistant`,
    response: JSON.stringify(
      {
        agent_id: "gpt-4-assistant",
        name: "GPT-4 Assistant",
        public_key: "ed25519:abc123...",
        trust_score: 0.92,
        attestation_count: 12,
        is_certified: true,
        last_checked: "2026-02-23T17:00:00Z",
        metadata: {},
        recent_attestations: [],
      },
      null,
      2
    ),
  },
  {
    method: "GET",
    path: "/api/v1/stats",
    title: "Platform Stats",
    description: "Platform-wide statistics: agents checked, attestations verified, average response time, uptime.",
    auth: false,
    params: [],
    curl: `curl https://api.isnad.dev/api/v1/stats`,
    response: JSON.stringify(
      { agents_checked: 1482, attestations_verified: 8391, avg_response_ms: 42.5, uptime: 864000.0 },
      null,
      2
    ),
  },
  {
    method: "GET",
    path: "/api/v1/health",
    title: "Health Check",
    description: "Returns 200 if the service is running. Use for monitoring.",
    auth: false,
    params: [],
    curl: `curl https://api.isnad.dev/api/v1/health`,
    response: JSON.stringify({ status: "ok", version: "0.3.0", modules: 36, tests: 1029 }, null, 2),
  },
  {
    method: "POST",
    path: "/api/v1/keys",
    title: "Generate API Key",
    description:
      "Generate a new API key. The raw key is returned once and only its hash is stored. Store it securely.",
    auth: false,
    params: [
      { name: "owner_email", type: "string", required: true, description: "Email of key owner" },
      { name: "rate_limit", type: "int", required: false, description: "Requests per minute (default: 100)" },
    ],
    curl: `curl -X POST https://api.isnad.dev/api/v1/keys \\
  -H "Content-Type: application/json" \\
  -d '{"owner_email": "you@example.com"}'`,
    response: JSON.stringify(
      {
        api_key: "isnad_a1b2c3d4e5f6...",
        owner_email: "you@example.com",
        rate_limit: 100,
        message: "Store this key securely — it won't be shown again.",
      },
      null,
      2
    ),
  },
  {
    method: "POST",
    path: "/api/v1/certify",
    title: "Request Certification",
    description: "Submit an agent for certification. Runs the full 36-module analysis and returns a trust report.",
    auth: true,
    params: [
      { name: "agent_id", type: "string", required: true, description: "Agent identifier" },
      { name: "name", type: "string", required: false, description: "Agent display name" },
      { name: "wallet", type: "string", required: false, description: "EVM wallet address for on-chain cert" },
      { name: "platform", type: "string", required: false, description: "Platform name" },
      { name: "capabilities", type: "string[]", required: false, description: "List of capabilities" },
      { name: "evidence_urls", type: "string[]", required: false, description: "External profile/repo URLs" },
    ],
    curl: `curl -X POST https://api.isnad.dev/api/v1/certify \\
  -H "X-API-Key: isnad_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"agent_id": "my-agent", "platform": "openai"}'`,
    response: JSON.stringify(
      {
        agent_id: "my-agent",
        overall_score: 58,
        confidence: "medium",
        risk_flags: ["no_attestations"],
        certified: false,
      },
      null,
      2
    ),
  },
  {
    method: "POST",
    path: "/api/v1/identity",
    title: "Create Identity",
    description: "Register a new cryptographic agent identity with an Ed25519 key pair.",
    auth: true,
    params: [
      { name: "agent_id", type: "string", required: true, description: "Unique agent identifier" },
      { name: "name", type: "string", required: false, description: "Display name" },
      { name: "metadata", type: "object", required: false, description: "Arbitrary metadata" },
    ],
    curl: `curl -X POST https://api.isnad.dev/api/v1/identity \\
  -H "X-API-Key: isnad_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"agent_id": "my-agent", "name": "My Agent"}'`,
    response: JSON.stringify(
      { agent_id: "my-agent", public_key: "ed25519:9f3a...", created: "2026-02-23T17:00:00Z" },
      null,
      2
    ),
  },
  {
    method: "POST",
    path: "/api/v1/attest",
    title: "Submit Attestation",
    description: "Submit a signed attestation about an agent. Adds to the trust chain.",
    auth: true,
    params: [
      { name: "subject", type: "string", required: true, description: "Agent being attested" },
      { name: "witness", type: "string", required: true, description: "Attesting agent/entity" },
      { name: "claim", type: "string", required: true, description: "Attestation claim" },
      { name: "signature", type: "string", required: true, description: "Ed25519 signature" },
    ],
    curl: `curl -X POST https://api.isnad.dev/api/v1/attest \\
  -H "X-API-Key: isnad_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"subject": "agent-a", "witness": "agent-b", "claim": "reliable", "signature": "base64..."}'`,
    response: JSON.stringify(
      { attestation_id: "att_9f3a...", subject: "agent-a", witness: "agent-b", recorded: true },
      null,
      2
    ),
  },
];

/* ── Components ── */

function MethodBadge({ method }: { method: Method }) {
  const color = method === "GET" ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : "bg-blue-500/20 text-blue-400 border-blue-500/30";
  return (
    <span className={`inline-block px-2 py-0.5 text-xs font-mono font-bold rounded border ${color}`}>
      {method}
    </span>
  );
}

function CodeBlock({ children, language = "" }: { children: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="relative group">
      <pre className="bg-[#0d1117] border border-white/10 rounded-xl p-4 overflow-x-auto text-sm leading-relaxed" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
        <code className="text-zinc-300">{children}</code>
      </pre>
      <button
        onClick={copy}
        className="absolute top-3 right-3 text-xs text-zinc-500 hover:text-zinc-300 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        {copied ? "Copied!" : "Copy"}
      </button>
    </div>
  );
}

function SideNav({ endpoints }: { endpoints: Endpoint[] }) {
  return (
    <nav className="hidden lg:block sticky top-24 w-56 shrink-0 max-h-[calc(100vh-8rem)] overflow-y-auto text-sm">
      <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">On this page</div>
      <ul className="space-y-1">
        <li><a href="#quick-start" className="block py-1 text-zinc-400 hover:text-isnad-teal transition-colors">Quick Start</a></li>
        <li><a href="#authentication" className="block py-1 text-zinc-400 hover:text-isnad-teal transition-colors">Authentication</a></li>
        <li>
          <a href="#endpoints" className="block py-1 text-zinc-400 hover:text-isnad-teal transition-colors">Endpoints</a>
          <ul className="ml-3 mt-1 space-y-1">
            {endpoints.map((ep) => (
              <li key={ep.path + ep.method}>
                <a href={`#${ep.path.replace(/[/{}]/g, "-").replace(/^-/, "")}`} className="block py-0.5 text-zinc-500 hover:text-isnad-teal transition-colors text-xs truncate">
                  <span className={ep.method === "GET" ? "text-emerald-500" : "text-blue-400"}>{ep.method}</span>{" "}
                  {ep.path.replace("/api/v1", "")}
                </a>
              </li>
            ))}
          </ul>
        </li>
        <li><a href="#rate-limits" className="block py-1 text-zinc-400 hover:text-isnad-teal transition-colors">Rate Limits</a></li>
        <li><a href="#sdks" className="block py-1 text-zinc-400 hover:text-isnad-teal transition-colors">SDKs</a></li>
      </ul>
    </nav>
  );
}

function EndpointCard({ ep }: { ep: Endpoint }) {
  const anchor = ep.path.replace(/[/{}]/g, "-").replace(/^-/, "");
  return (
    <div id={anchor} className="scroll-mt-24">
      <Card className="space-y-5">
        <div className="flex items-center gap-3 flex-wrap">
          <MethodBadge method={ep.method} />
          <code className="text-base font-mono text-zinc-200">{ep.path}</code>
          {ep.auth && (
            <span className="text-xs text-amber-400 border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 rounded">
              Requires API Key
            </span>
          )}
        </div>
        <p className="text-zinc-400 text-sm">{ep.description}</p>

        {ep.params.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-zinc-500 border-b border-white/10">
                  <th className="pb-2 pr-4 font-medium">Parameter</th>
                  <th className="pb-2 pr-4 font-medium">Type</th>
                  <th className="pb-2 pr-4 font-medium">Required</th>
                  <th className="pb-2 font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {ep.params.map((p) => (
                  <tr key={p.name} className="border-b border-white/5">
                    <td className="py-2 pr-4 font-mono text-isnad-teal text-xs">{p.name}</td>
                    <td className="py-2 pr-4 text-zinc-400 text-xs">{p.type}</td>
                    <td className="py-2 pr-4 text-xs">{p.required ? <span className="text-amber-400">Yes</span> : <span className="text-zinc-500">No</span>}</td>
                    <td className="py-2 text-zinc-400 text-xs">{p.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="space-y-2">
          <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Request</div>
          <CodeBlock language="bash">{ep.curl}</CodeBlock>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Response</div>
          <CodeBlock language="json">{ep.response}</CodeBlock>
        </div>
      </Card>
    </div>
  );
}

/* ── Page ── */
export default function DocsPage() {
  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 pb-20 px-6">
        <div className="max-w-6xl mx-auto flex gap-10">
          <SideNav endpoints={endpoints} />

          <div className="flex-1 min-w-0 space-y-16">
            {/* Header */}
            <div>
              <h1 className="text-4xl font-bold mb-3">API Documentation</h1>
              <p className="text-zinc-400 text-lg">
                Everything you need to integrate isnad trust verification into your application.
              </p>
              <div className="flex gap-3 mt-4">
                <span className="text-xs font-mono bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-zinc-400">
                  Base URL: <span className="text-isnad-teal">https://api.isnad.dev</span>
                </span>
                <span className="text-xs font-mono bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-zinc-400">
                  Version: <span className="text-isnad-teal">v0.3.0</span>
                </span>
              </div>
            </div>

            {/* Quick Start */}
            <section id="quick-start" className="scroll-mt-24 space-y-6">
              <h2 className="text-2xl font-bold">Quick Start</h2>
              <div className="grid gap-4">
                {[
                  {
                    step: 1,
                    title: "Get an API key",
                    content: `curl -X POST https://api.isnad.dev/api/v1/keys \\
  -H "Content-Type: application/json" \\
  -d '{"owner_email": "you@example.com"}'`,
                  },
                  {
                    step: 2,
                    title: "Make your first trust check",
                    content: `curl https://api.isnad.dev/api/v1/check/gpt-4-assistant`,
                  },
                  {
                    step: 3,
                    title: "Read the response",
                    content: `{
  "agent_id": "gpt-4-assistant",
  "overall_score": 72,
  "confidence": "medium",
  "certified": true
}`,
                  },
                ].map((s) => (
                  <Card key={s.step} glow={false} className="space-y-3">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center justify-center w-7 h-7 rounded-full bg-isnad-teal/20 text-isnad-teal text-sm font-bold">
                        {s.step}
                      </span>
                      <span className="font-semibold">{s.title}</span>
                    </div>
                    <CodeBlock>{s.content}</CodeBlock>
                  </Card>
                ))}
              </div>
            </section>

            {/* Authentication */}
            <section id="authentication" className="scroll-mt-24 space-y-4">
              <h2 className="text-2xl font-bold">Authentication</h2>
              <Card glow={false} className="space-y-3">
                <p className="text-zinc-400 text-sm">
                  Public endpoints (<code className="text-isnad-teal">/check</code>, <code className="text-isnad-teal">/explorer</code>, <code className="text-isnad-teal">/stats</code>, <code className="text-isnad-teal">/health</code>) require no authentication.
                </p>
                <p className="text-zinc-400 text-sm">
                  Write endpoints (<code className="text-isnad-teal">/certify</code>, <code className="text-isnad-teal">/identity</code>, <code className="text-isnad-teal">/attest</code>) require an API key via the <code className="text-isnad-teal font-mono">X-API-Key</code> header:
                </p>
                <CodeBlock>{`curl -H "X-API-Key: isnad_YOUR_KEY" https://api.isnad.dev/api/v1/certify`}</CodeBlock>
                <p className="text-zinc-400 text-sm">
                  Generate a key via <code className="text-isnad-teal">POST /api/v1/keys</code>. The raw key is shown only once — store it securely.
                </p>
              </Card>
            </section>

            {/* Endpoints Reference */}
            <section id="endpoints" className="scroll-mt-24 space-y-8">
              <h2 className="text-2xl font-bold">Endpoints Reference</h2>
              {endpoints.map((ep) => (
                <EndpointCard key={ep.path + ep.method} ep={ep} />
              ))}
            </section>

            {/* Rate Limits */}
            <section id="rate-limits" className="scroll-mt-24 space-y-4">
              <h2 className="text-2xl font-bold">Rate Limits</h2>
              <Card glow={false} className="space-y-3">
                <p className="text-zinc-400 text-sm">
                  Default rate limit: <span className="text-zinc-200 font-semibold">60 requests/minute</span> per IP, with a burst allowance of 10 requests.
                </p>
                <p className="text-zinc-400 text-sm">
                  API key holders receive their configured rate limit (default: 100 req/min). Higher-trust agents may receive elevated limits via the trust-based rate limiting system.
                </p>
                <p className="text-zinc-400 text-sm">
                  When rate-limited, the API returns <code className="text-amber-400">429 Too Many Requests</code>. Implement exponential backoff in your client.
                </p>
              </Card>
            </section>

            {/* SDKs */}
            <section id="sdks" className="scroll-mt-24 space-y-6">
              <h2 className="text-2xl font-bold">SDKs &amp; Examples</h2>
              <SdkTabs />
            </section>
          </div>
        </div>
      </main>
    </>
  );
}

function SdkTabs() {
  const [tab, setTab] = useState<"python" | "javascript">("python");

  const python = `import requests

# Trust check
resp = requests.get("https://api.isnad.dev/api/v1/check/gpt-4-assistant")
data = resp.json()
print(f"Score: {data['overall_score']}, Certified: {data['certified']}")

# Generate API key
resp = requests.post(
    "https://api.isnad.dev/api/v1/keys",
    json={"owner_email": "you@example.com"}
)
api_key = resp.json()["api_key"]

# Submit attestation (authenticated)
requests.post(
    "https://api.isnad.dev/api/v1/attest",
    headers={"X-API-Key": api_key},
    json={
        "subject": "agent-a",
        "witness": "agent-b",
        "claim": "reliable",
        "signature": "base64..."
    }
)`;

  const javascript = `// Trust check
const resp = await fetch("https://api.isnad.dev/api/v1/check/gpt-4-assistant");
const data = await resp.json();
console.log(\`Score: \${data.overall_score}, Certified: \${data.certified}\`);

// Generate API key
const keyResp = await fetch("https://api.isnad.dev/api/v1/keys", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ owner_email: "you@example.com" }),
});
const { api_key } = await keyResp.json();

// Submit attestation (authenticated)
await fetch("https://api.isnad.dev/api/v1/attest", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": api_key,
  },
  body: JSON.stringify({
    subject: "agent-a",
    witness: "agent-b",
    claim: "reliable",
    signature: "base64...",
  }),
});`;

  return (
    <Card glow={false} className="space-y-4">
      <div className="flex gap-2">
        {(["python", "javascript"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 text-sm rounded-lg font-medium transition-colors ${
              tab === t ? "bg-isnad-teal/20 text-isnad-teal" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t === "python" ? "Python" : "JavaScript"}
          </button>
        ))}
      </div>
      <CodeBlock language={tab}>{tab === "python" ? python : javascript}</CodeBlock>
    </Card>
  );
}
