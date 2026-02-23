import type { Agent, TrustCheckResult } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export async function checkAgent(agentId: string): Promise<TrustCheckResult> {
  const res = await fetch(`${API_BASE}/check/${encodeURIComponent(agentId)}`);
  if (!res.ok) throw new Error(`Check failed: ${res.status}`);
  return res.json();
}

export async function getExplorer(
  page: number,
  search?: string
): Promise<{ agents: Agent[]; total: number }> {
  const params = new URLSearchParams({ page: String(page) });
  if (search) params.set("search", search);
  const res = await fetch(`${API_BASE}/explorer?${params}`);
  if (!res.ok) throw new Error(`Explorer failed: ${res.status}`);
  return res.json();
}

export async function getStats(): Promise<{
  agentsChecked: number;
  attestationsVerified: number;
  avgResponseMs: number;
}> {
  const res = await fetch(`${API_BASE}/stats`);
  if (!res.ok) throw new Error(`Stats failed: ${res.status}`);
  return res.json();
}
