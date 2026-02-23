import type { Agent, TrustCheckResult } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

const LEGACY_API =
  process.env.NEXT_PUBLIC_LEGACY_API_URL || "http://localhost:8000";

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

export interface StatsResponse {
  total_identities: number;
  total_attestations: number;
  unique_agents_in_chain: number;
  unique_scopes: number;
}

export async function getStats(): Promise<StatsResponse> {
  const res = await fetch(`${LEGACY_API}/stats`);
  if (!res.ok) throw new Error(`Stats failed: ${res.status}`);
  return res.json();
}

export interface CreateIdentityRequest {
  name: string;
  platform: string;
  platform_handle: string;
  public_key?: string;
}

export interface CreateIdentityResponse {
  agent_id: string;
  public_key: string;
}

export async function createIdentity(
  _data: CreateIdentityRequest
): Promise<CreateIdentityResponse> {
  const res = await fetch(`${LEGACY_API}/identities`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Create identity failed: ${err}`);
  }
  return res.json();
}

export interface IdentityListItem {
  agent_id: string;
  public_key: string;
}

export async function listIdentities(): Promise<{
  identities: IdentityListItem[];
  count: number;
}> {
  const res = await fetch(`${LEGACY_API}/identities`);
  if (!res.ok) throw new Error(`List identities failed: ${res.status}`);
  return res.json();
}

export interface TrustScoreResponse {
  agent_id: string;
  score: number;
  attestation_count: number;
}

export async function getTrustScore(
  agentId: string
): Promise<TrustScoreResponse> {
  const res = await fetch(
    `${LEGACY_API}/trust/${encodeURIComponent(agentId)}`
  );
  if (!res.ok) throw new Error(`Trust score failed: ${res.status}`);
  return res.json();
}

export interface IdentityDetail {
  agent_id: string;
  public_key: string;
  trust_score: number;
}

export async function getIdentity(
  agentId: string
): Promise<IdentityDetail> {
  const res = await fetch(
    `${LEGACY_API}/identities/${encodeURIComponent(agentId)}`
  );
  if (!res.ok) throw new Error(`Identity not found: ${res.status}`);
  return res.json();
}
