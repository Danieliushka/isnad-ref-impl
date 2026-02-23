import type { Agent, TrustScore } from "./types";

export const recentlyChecked = [
  { id: "gpt-4o", name: "GPT-4o", score: 92, checked: "2 min ago" },
  { id: "claude-3-5", name: "Claude 3.5", score: 89, checked: "5 min ago" },
  { id: "gendolf", name: "Gendolf", score: 87, checked: "15 min ago" },
  { id: "perplexity", name: "Perplexity", score: 83, checked: "1h ago" },
  { id: "gemini-pro", name: "Gemini Pro", score: 78, checked: "3h ago" },
];

export type AgentStatus = "certified" | "pending" | "failed";

export interface ExplorerAgent {
  agent: Agent;
  score: TrustScore;
  status: AgentStatus;
  lastChecked: Date;
}

function hoursAgo(h: number): Date {
  return new Date(Date.now() - h * 3600_000);
}

function makeAgent(
  name: string,
  overall: number,
  status: AgentStatus,
  hoursBack: number,
  cats: TrustScore["categories"],
): ExplorerAgent {
  const id = name.toLowerCase().replace(/[\s.]+/g, "-");
  return {
    agent: {
      id,
      name,
      publicKey: `0x${id.slice(0, 8).padEnd(8, "0")}...${id.slice(-4).padStart(4, "f")}`,
      createdAt: new Date("2025-01-15").toISOString(),
      trustScore: overall,
      isCertified: status === "certified",
    },
    score: {
      overall,
      confidence: overall >= 80 ? "high" : overall >= 60 ? "medium" : "low",
      categories: cats,
    },
    status,
    lastChecked: hoursAgo(hoursBack),
  };
}

export interface MockAgentDetail {
  name: string;
  publicKey: string;
  score: number;
  status: string;
  confidence: "high" | "medium" | "low";
  categories: Record<string, number>;
  riskFlags: string[];
  attestationHistory: { task: string; witness: string; date: string; score: number }[];
}

function makeMockDetail(name: string, overall: number, status: string): MockAgentDetail {
  const conf = overall >= 80 ? "high" as const : overall >= 60 ? "medium" as const : "low" as const;
  return {
    name,
    publicKey: `0x${Array.from({ length: 8 }, () => Math.floor(Math.random() * 16).toString(16)).join("")}`,
    score: overall,
    status,
    confidence: conf,
    categories: {
      identity: +(Math.random() * 0.3 + 0.6).toFixed(2),
      attestation: +(Math.random() * 0.3 + 0.55).toFixed(2),
      behavioral: +(Math.random() * 0.3 + 0.5).toFixed(2),
      platform: +(Math.random() * 0.3 + 0.5).toFixed(2),
      transactions: +(Math.random() * 0.3 + 0.5).toFixed(2),
      security: +(Math.random() * 0.3 + 0.55).toFixed(2),
    },
    riskFlags: overall < 60 ? ["Low attestation coverage", "Limited transaction history"] : [],
    attestationHistory: [
      { task: "Identity verification", witness: "OpenAI Registry", date: "2025-01-20", score: Math.min(99, overall + 3) },
      { task: "Behavioral audit", witness: "isnad Validator", date: "2025-01-18", score: overall },
      { task: "Platform check", witness: "Agent Hub", date: "2025-01-15", score: Math.max(20, overall - 5) },
    ],
  };
}

const detailDb: Record<string, MockAgentDetail> = {};
const agentList = [
  ["GPT-4o", 92, "Certified"], ["Claude 3.5", 89, "Certified"], ["Gendolf", 87, "Certified"],
  ["Perplexity", 83, "Certified"], ["Gemini Pro", 78, "Pending"], ["Cohere Command", 76, "Pending"],
  ["Qwen-2", 73, "Pending"], ["Mistral Large", 71, "Pending"], ["Phi-3", 67, "Pending"],
  ["Llama 3", 65, "Failed"], ["Grok-2", 58, "Failed"], ["DeepSeek-V3", 44, "Failed"],
] as const;

for (const [name, score, status] of agentList) {
  const id = (name as string).toLowerCase().replace(/[\s.]+/g, "-");
  detailDb[id] = makeMockDetail(name as string, score as number, status as string);
}

export function getAgent(id: string): MockAgentDetail {
  return detailDb[id] ?? makeMockDetail(id, 50, "Pending");
}

export function getGrade(score: number): string {
  if (score >= 90) return "A+";
  if (score >= 80) return "A";
  if (score >= 70) return "B";
  if (score >= 60) return "C";
  if (score >= 50) return "D";
  return "F";
}

export const mockAgents: ExplorerAgent[] = [
  makeAgent("GPT-4o", 92, "certified", 0.5, { identity: 0.95, attestation: 0.91, behavioral: 0.93, platform: 0.88, transactions: 0.9, security: 0.94 }),
  makeAgent("Claude 3.5", 89, "certified", 1, { identity: 0.92, attestation: 0.88, behavioral: 0.91, platform: 0.85, transactions: 0.87, security: 0.91 }),
  makeAgent("Gendolf", 87, "certified", 2, { identity: 0.9, attestation: 0.86, behavioral: 0.89, platform: 0.84, transactions: 0.85, security: 0.88 }),
  makeAgent("Perplexity", 83, "certified", 3, { identity: 0.87, attestation: 0.82, behavioral: 0.84, platform: 0.8, transactions: 0.81, security: 0.85 }),
  makeAgent("Gemini Pro", 78, "pending", 5, { identity: 0.82, attestation: 0.76, behavioral: 0.79, platform: 0.74, transactions: 0.77, security: 0.8 }),
  makeAgent("Cohere Command", 76, "pending", 8, { identity: 0.8, attestation: 0.74, behavioral: 0.77, platform: 0.72, transactions: 0.75, security: 0.78 }),
  makeAgent("Qwen-2", 73, "pending", 12, { identity: 0.78, attestation: 0.71, behavioral: 0.74, platform: 0.7, transactions: 0.72, security: 0.75 }),
  makeAgent("Mistral Large", 71, "pending", 18, { identity: 0.76, attestation: 0.69, behavioral: 0.72, platform: 0.68, transactions: 0.7, security: 0.73 }),
  makeAgent("Phi-3", 67, "pending", 24, { identity: 0.72, attestation: 0.65, behavioral: 0.68, platform: 0.64, transactions: 0.66, security: 0.69 }),
  makeAgent("Llama 3", 65, "failed", 36, { identity: 0.7, attestation: 0.63, behavioral: 0.66, platform: 0.62, transactions: 0.64, security: 0.67 }),
  makeAgent("Grok-2", 58, "failed", 48, { identity: 0.64, attestation: 0.56, behavioral: 0.59, platform: 0.55, transactions: 0.57, security: 0.6 }),
  makeAgent("DeepSeek-V3", 44, "failed", 72, { identity: 0.5, attestation: 0.42, behavioral: 0.45, platform: 0.4, transactions: 0.43, security: 0.46 }),
];

// Lookup by id for /check/[id] page
export function getAgentById(id: string): ExplorerAgent | undefined {
  return mockAgents.find((a) => a.agent.id === id);
}

export interface AttestationEntry {
  witness: string;
  task: string;
  score: number;
  date: string;
}

export const mockAttestations: Record<string, AttestationEntry[]> = {
  'gpt-4o': [
    { witness: 'Claude 3.5', task: 'Code review audit', score: 94, date: '2026-02-22T14:30:00Z' },
    { witness: 'Gemini Pro', task: 'API response validation', score: 88, date: '2026-02-20T09:15:00Z' },
    { witness: 'Llama 3', task: 'Data processing pipeline', score: 82, date: '2026-02-18T16:45:00Z' },
    { witness: 'Claude 3.5', task: 'Security assessment', score: 91, date: '2026-02-15T11:00:00Z' },
    { witness: 'Gemini Pro', task: 'Multi-modal analysis', score: 86, date: '2026-02-12T08:20:00Z' },
  ],
  'claude-3-5': [
    { witness: 'GPT-4o', task: 'Reasoning benchmark', score: 96, date: '2026-02-23T10:00:00Z' },
    { witness: 'Gemini Pro', task: 'Safety evaluation', score: 93, date: '2026-02-21T13:30:00Z' },
    { witness: 'GPT-4o', task: 'Code generation audit', score: 90, date: '2026-02-19T15:00:00Z' },
    { witness: 'Llama 3', task: 'Instruction following', score: 88, date: '2026-02-17T09:45:00Z' },
    { witness: 'Gemini Pro', task: 'Cross-lingual task', score: 91, date: '2026-02-14T12:00:00Z' },
  ],
};

export const defaultAttestations: AttestationEntry[] = [
  { witness: 'GPT-4o', task: 'General capability test', score: 75, date: '2026-02-20T12:00:00Z' },
  { witness: 'Claude 3.5', task: 'Safety evaluation', score: 70, date: '2026-02-18T10:00:00Z' },
  { witness: 'Gemini Pro', task: 'Reasoning benchmark', score: 72, date: '2026-02-15T14:00:00Z' },
];

export const mockRiskFlags: Record<string, string[]> = {
  'llama-3': ['Insufficient attestation history', 'Open-weight model — provenance unverifiable'],
  'grok-2': ['Platform presence score declining', 'Limited transaction history'],
  'deepseek-v3': ['Identity not verified', 'No attestation chain found', 'Suspicious behavioral patterns detected', 'No platform presence records'],
};
