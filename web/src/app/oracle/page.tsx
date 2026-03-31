'use client';

import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useState } from 'react';

const PROGRAM_ID = 'BhG84286N1HTG6cRmASZVNQNtFd7K98BsBrhfjYc7H31';
const RPC = 'https://api.devnet.solana.com';

const B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
function b58encode(bytes: Uint8Array): string {
  let n = 0n;
  for (const b of bytes) n = n * 256n + BigInt(b);
  let s = '';
  while (n > 0n) { s = B58[Number(n % 58n)] + s; n /= 58n; }
  for (const b of bytes) { if (b === 0) s = '1' + s; else break; }
  return s;
}

async function findPDA(seeds: Uint8Array[]): Promise<string> {
  const programBytes = new Uint8Array(32);
  // Decode program ID from base58
  let n = 0n;
  for (const c of PROGRAM_ID) n = n * 58n + BigInt(B58.indexOf(c));
  const hex = n.toString(16).padStart(64, '0');
  for (let i = 0; i < 32; i++) programBytes[i] = parseInt(hex.slice(i*2, i*2+2), 16);

  for (let bump = 255; bump >= 0; bump--) {
    const combined = new Uint8Array([
      ...seeds.reduce<number[]>((a, s) => [...a, ...s], []),
      bump,
      ...programBytes,
      ...new TextEncoder().encode('ProgramDerivedAddress'),
    ]);
    const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', combined));
    return b58encode(hash);
  }
  return '';
}

interface TrustScore {
  agentId: string;
  overall: number;
  provenance: number;
  trackRecord: number;
  presence: number;
  endorsements: number;
  tier: number;
  evidenceHash: string;
  teeType: number;
  infraScore: number;
  infraVerified: boolean;
  measurementsMatch: boolean;
}

const tierNames: Record<number, string> = { 0: 'UNKNOWN', 1: 'EMERGING', 2: 'ESTABLISHED', 3: 'VERIFIED' };
const tierColors: Record<number, string> = { 
  0: 'bg-zinc-700 text-zinc-300',
  1: 'bg-emerald-900/50 text-emerald-400',
  2: 'bg-blue-900/50 text-blue-400',
  3: 'bg-purple-900/50 text-purple-400',
};
const teeNames: Record<number, string> = { 0: 'None', 1: 'SGX', 2: 'SEV', 3: 'Nitro', 4: 'TrustZone', 5: 'CCA' };

function parseTrustScore(data: Uint8Array): TrustScore | null {
  if (!data || data.length < 50) return null;
  let offset = 8;
  const idLen = data[offset] | (data[offset+1] << 8) | (data[offset+2] << 16) | (data[offset+3] << 24);
  offset += 4;
  const agentId = new TextDecoder().decode(data.slice(offset, offset + idLen));
  offset += idLen;
  const overall = data[offset++];
  const provenance = data[offset++];
  const trackRecord = data[offset++];
  const presence = data[offset++];
  const endorsements = data[offset++];
  const tier = data[offset++];
  const evidenceHash = Array.from(data.slice(offset, offset + 32)).map(b => b.toString(16).padStart(2, '0')).join('');
  offset += 32;
  offset += 32; // authority
  offset += 8;  // updated_at
  const teeType = data[offset++];
  const infraScore = data[offset++];
  const infraVerified = data[offset++] === 1;
  const measurementsMatch = data[offset++] === 1;
  return { agentId, overall, provenance, trackRecord, presence, endorsements, tier, evidenceHash, teeType, infraScore, infraVerified, measurementsMatch };
}

function DimensionBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="text-center">
      <div className="text-xs text-zinc-500 uppercase tracking-wider">{label}</div>
      <div className="text-lg font-semibold mt-1">{value}</div>
      <div className="h-1.5 bg-zinc-800 rounded-full mt-2 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%`, transition: 'width 0.5s' }} />
      </div>
    </div>
  );
}

export default function OraclePage() {
  const [query, setQuery] = useState('');
  const [score, setScore] = useState<TrustScore | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pda, setPda] = useState('');

  async function search() {
    if (!query.trim()) return;
    setLoading(true);
    setError('');
    setScore(null);

    try {
      const seeds = [new TextEncoder().encode('trust_score'), new TextEncoder().encode(query.trim())];
      const address = await findPDA(seeds);
      setPda(address);

      const resp = await fetch(RPC, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'getAccountInfo', params: [address, { encoding: 'base64' }] }),
      });
      const data = await resp.json();

      if (!data.result?.value?.data?.[0]) {
        setError('Agent not found on-chain');
        return;
      }

      const raw = atob(data.result.value.data[0]);
      const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
      const parsed = parseTrustScore(bytes);
      if (!parsed) { setError('Failed to parse score data'); return; }
      setScore(parsed);
    } catch (e: unknown) {
      setError(`Error: ${e instanceof Error ? e.message : 'Unknown'}`);
    } finally {
      setLoading(false);
    }
  }

  const weighted = score ? Math.round(
    score.provenance * 0.25 + score.trackRecord * 0.30 + score.presence * 0.17 +
    score.endorsements * 0.13 + score.infraScore * 0.15
  ) : 0;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <Navbar />
      
      {/* Header */}
      <div className="border-b border-zinc-800 bg-gradient-to-b from-zinc-900 to-zinc-950">
        <div className="max-w-4xl mx-auto px-4 py-16 text-center">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-cyan-400 bg-clip-text text-transparent">
            🔮 Trust Oracle
          </h1>
          <p className="text-zinc-400 mt-3 text-lg">
            On-chain trust scoring for AI agents on Solana
          </p>
          <div className="mt-2">
            <Badge className="text-xs text-zinc-500 border-zinc-700">
              devnet · Program: {PROGRAM_ID.slice(0, 8)}...
            </Badge>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="max-w-2xl mx-auto px-4 -mt-6">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            placeholder="Enter agent ID (e.g. gendolf-demo-...)"
            className="flex-1 px-4 py-3 bg-zinc-900 border border-zinc-700 rounded-xl text-zinc-100 placeholder:text-zinc-600 focus:border-purple-500 focus:outline-none transition"
          />
          <button
            onClick={search}
            disabled={loading}
            className="px-6 py-3 bg-purple-600 hover:bg-purple-500 rounded-xl font-medium transition disabled:opacity-50"
          >
            {loading ? '...' : 'Search'}
          </button>
        </div>
      </div>

      {/* Results */}
      <div className="max-w-2xl mx-auto px-4 mt-6 pb-16">
        {error && (
          <Card className="bg-zinc-900/50 border-zinc-800 p-6 text-center">
            <p className="text-zinc-400">{error}</p>
            {pda && <p className="text-xs text-zinc-600 mt-2 font-mono">PDA: {pda}</p>}
          </Card>
        )}

        {score && (
          <Card className="bg-zinc-900/50 border-zinc-800 p-6">
            {/* Header */}
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-semibold">{score.agentId}</h2>
              <span className={`px-3 py-1 rounded-full text-xs font-semibold uppercase ${tierColors[score.tier]}`}>
                {tierNames[score.tier]}
              </span>
            </div>

            {/* Overall Score */}
            <div className="text-center my-8">
              <div className="text-6xl font-extrabold">{weighted}</div>
              <div className="text-zinc-500 text-sm mt-1">Weighted Score (v4)</div>
            </div>

            {/* Dimensions */}
            <div className="grid grid-cols-5 gap-4 mb-6">
              <DimensionBar label="Provenance" value={score.provenance} color="bg-amber-500" />
              <DimensionBar label="Track Record" value={score.trackRecord} color="bg-emerald-500" />
              <DimensionBar label="Presence" value={score.presence} color="bg-blue-500" />
              <DimensionBar label="Endorsements" value={score.endorsements} color="bg-violet-500" />
              <DimensionBar label="🔐 Infra" value={score.infraScore} color="bg-red-500" />
            </div>

            {/* TEE Section */}
            {score.teeType > 0 && (
              <div className="bg-zinc-800/50 rounded-lg p-4 border border-zinc-700">
                <div className="flex items-center gap-3">
                  <span className="text-lg">🔐</span>
                  <span className="font-semibold">{teeNames[score.teeType]} Enclave</span>
                  <span className="text-sm">·</span>
                  <span className="text-sm">{score.infraVerified ? '✅ Verified' : '❌ Unverified'}</span>
                  <span className="text-sm">·</span>
                  <span className="text-sm">{score.measurementsMatch ? '✅ Measurements Match' : '❌ Mismatch'}</span>
                </div>
              </div>
            )}

            {/* Evidence */}
            <div className="mt-4 text-xs text-zinc-600 font-mono break-all">
              Evidence: 0x{score.evidenceHash}
              <br />PDA: {pda}
            </div>
          </Card>
        )}

        {/* How It Works */}
        {!score && !error && (
          <div className="grid grid-cols-4 gap-4 mt-12">
            {[
              { icon: '📊', title: 'Score', desc: 'Multi-dimensional trust analysis across 5 dimensions' },
              { icon: '🛡️', title: 'Certify', desc: 'Red-team adversarial testing with 37 attack vectors' },
              { icon: '🔐', title: 'Attest', desc: 'TEE verification proves secure enclave execution' },
              { icon: '⛓️', title: 'Verify', desc: 'Any Solana program can query trust in one call' },
            ].map(step => (
              <Card key={step.title} className="bg-zinc-900/50 border-zinc-800 p-5 text-center">
                <div className="text-3xl mb-3">{step.icon}</div>
                <div className="font-semibold">{step.title}</div>
                <div className="text-xs text-zinc-500 mt-2">{step.desc}</div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
