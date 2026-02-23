export interface Agent {
  id: string;
  name: string;
  publicKey: string;
  createdAt: string;
  trustScore: number | null;
  isCertified: boolean;
}

export interface TrustScore {
  overall: number;
  confidence: "high" | "medium" | "low";
  categories: {
    identity: number;
    attestation: number;
    behavioral: number;
    platform: number;
    transactions: number;
    security: number;
  };
}

export interface Certification {
  id: string;
  agentId: string;
  score: number;
  certified: boolean;
  issuedAt: string;
  expiresAt: string;
  details: TrustScore;
}

export interface TrustCheckResult {
  agent: Agent;
  score: TrustScore;
  riskFlags: string[];
  attestationCount: number;
  lastChecked: string;
}
