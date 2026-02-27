import type { Agent, TrustCheckResult } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "/api/v1";

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
  const res = await fetch(`${API_BASE}/stats`);
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
  data: CreateIdentityRequest
): Promise<CreateIdentityResponse> {
  const res = await fetch(`${API_BASE}/identities`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
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
  const res = await fetch(`${API_BASE}/identities`);
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
    `${API_BASE}/trust/${encodeURIComponent(agentId)}`
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
    `${API_BASE}/identities/${encodeURIComponent(agentId)}`
  );
  if (!res.ok) throw new Error(`Identity not found: ${res.status}`);
  return res.json();
}

/* ── Agent Registration ── */

export interface PlatformEntry {
  name: string;
  url: string;
}

export interface RegisterAgentRequest {
  name: string;
  description: string;
  agent_type: "autonomous" | "tool-calling" | "human-supervised";
  platforms: PlatformEntry[];
  capabilities: string[];
  offerings: string;
  avatar_url?: string;
  contact_email?: string;
}

export interface RegisterAgentResponse {
  agent_id: string;
  public_key: string;
  api_key: string;
  created_at: string;
  message: string;
}

export async function registerAgent(
  data: RegisterAgentRequest
): Promise<RegisterAgentResponse> {
  const res = await fetch(`${API_BASE}/agents/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Registration failed" }));
    throw new Error(err.detail || "Registration failed");
  }
  return res.json();
}

export interface AgentProfile {
  agent_id: string;
  name: string;
  description: string;
  agent_type: string;
  public_key: string;
  platforms: PlatformEntry[];
  capabilities: string[];
  offerings: string;
  avatar_url: string | null;
  contact_email: string | null;
  trust_score: number;
  is_certified: boolean;
  created_at: string;
}

export interface AgentListResponse {
  agents: AgentProfile[];
  total: number;
  page: number;
  limit: number;
}

export async function listAgents(params?: {
  page?: number;
  limit?: number;
  agent_type?: string;
  platform?: string;
  search?: string;
}): Promise<AgentListResponse> {
  const sp = new URLSearchParams();
  if (params?.page) sp.set("page", String(params.page));
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.agent_type) sp.set("agent_type", params.agent_type);
  if (params?.platform) sp.set("platform", params.platform);
  if (params?.search) sp.set("search", params.search);
  const res = await fetch(`${API_BASE}/agents?${sp}`);
  if (!res.ok) throw new Error(`List agents failed: ${res.status}`);
  return res.json();
}

export async function getAgentProfile(agentId: string): Promise<AgentProfile> {
  const res = await fetch(`${API_BASE}/agents/${encodeURIComponent(agentId)}`);
  if (!res.ok) throw new Error(`Agent not found: ${res.status}`);
  return res.json();
}

export async function updateAgentProfile(
  agentId: string,
  apiKey: string,
  data: Partial<RegisterAgentRequest>
): Promise<AgentProfile> {
  const res = await fetch(`${API_BASE}/agents/${encodeURIComponent(agentId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Update failed" }));
    throw new Error(err.detail || "Update failed");
  }
  return res.json();
}

/* ── Agent Explorer Detail ── */

export interface AgentDetailResponse {
  agent_id: string;
  name: string;
  public_key: string;
  trust_score: number;
  attestation_count: number;
  is_certified: boolean;
  last_checked: string | null;
  metadata: {
    agent_type?: string;
    description?: string;
    platforms?: PlatformEntry[];
    capabilities?: string[];
    offerings?: string;
    avatar_url?: string;
    contact_email?: string;
  };
  recent_attestations: Array<{
    attestation_id: string;
    attester_id: string;
    attester_name: string;
    scope: string;
    value: number;
    created_at: string;
  }>;
}

export async function getAgentDetail(agentId: string): Promise<AgentDetailResponse> {
  const res = await fetch(`${API_BASE}/explorer/${encodeURIComponent(agentId)}`);
  if (!res.ok) throw new Error(`Agent not found: ${res.status}`);
  return res.json();
}

/* ── Trust Score v2 (real platform data) ── */

export interface SignalDetail {
  score: number;
  weight: number;
  confidence: number;
  effective_weight: number;
  evidence: Record<string, unknown>;
}

export interface TrustScoreV2Response {
  agent_id: string;
  trust_score: number;
  version: string;
  signals: {
    platform_reputation: SignalDetail;
    delivery_track_record: SignalDetail;
    identity_verification: SignalDetail;
    cross_platform_consistency: SignalDetail;
  };
  total_confidence: number;
  platforms_checked: string[];
}

/* ── Badges ── */

export interface BadgeRecord {
  id: string;
  agent_id: string;
  badge_type: string;
  status: string;
  granted_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export async function getAgentBadges(agentId: string): Promise<BadgeRecord[]> {
  const res = await fetch(`${API_BASE}/agents/${encodeURIComponent(agentId)}/badges`);
  if (!res.ok) return []; // graceful fallback
  return res.json();
}

export async function getTrustScoreV2(
  agentId: string
): Promise<TrustScoreV2Response> {
  const res = await fetch(
    `${API_BASE}/trust-score-v2/${encodeURIComponent(agentId)}`
  );
  if (!res.ok) throw new Error(`Trust score v2 failed: ${res.status}`);
  return res.json();
}

/* ── Trust Report (verification history) ── */

export interface TrustReportScore {
  score: number;
  evidence: Record<string, unknown>;
}

export interface TrustReport {
  agent_id: string;
  overall_score: number;
  decay_factor: number;
  platform_count: number;
  scores: {
    identity: TrustReportScore;
    activity: TrustReportScore;
    reputation: TrustReportScore;
    security: TrustReportScore;
  };
  computed_at: string;
}

export async function getTrustReport(agentId: string): Promise<TrustReport> {
  const res = await fetch(`${API_BASE}/agents/${encodeURIComponent(agentId)}/trust-report`);
  if (!res.ok) throw new Error(`Trust report failed: ${res.status}`);
  return res.json();
}
