'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, TrustBadgeLarge } from '@/components/ui/badge';
import TrustScoreRing from '@/components/trust-score-ring';
import RadarChart from '@/components/radar-chart';
import { getAgentProfile, getTrustScoreV2, getAgentBadges, getAgentDetail, getTrustReport, type AgentProfile, type TrustScoreV2Response, type BadgeRecord, type AgentDetailResponse, type TrustReport } from '@/lib/api';

const typeLabels: Record<string, { label: string; color: string }> = {
  autonomous: { label: 'Autonomous', color: 'text-purple-400 bg-purple-500/15 border-purple-500/20' },
  'tool-calling': { label: 'Tool-Calling', color: 'text-blue-400 bg-blue-500/15 border-blue-500/20' },
  'human-supervised': { label: 'Human-Supervised', color: 'text-amber-400 bg-amber-500/15 border-amber-500/20' },
};

// SVG platform icons — clean, no emoji
function PlatformIcon({ name, className = "w-5 h-5" }: { name: string; className?: string }) {
  const key = name.toLowerCase();
  const strokeProps = { fill: "none", viewBox: "0 0 24 24", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, className };

  if (key === 'github') return (
    <svg {...strokeProps} viewBox="0 0 24 24" fill="currentColor" stroke="none">
      <path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0012 2z"/>
    </svg>
  );
  if (key === 'ugig') return (
    <svg {...strokeProps}><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
  );
  if (key === 'telegram') return (
    <svg {...strokeProps} viewBox="0 0 24 24" fill="currentColor" stroke="none">
      <path d="M20.665 3.717l-17.73 6.837c-1.21.486-1.203 1.161-.222 1.462l4.552 1.42 10.532-6.645c.498-.303.953-.14.579.192l-8.533 7.701h-.002l.002.001-.314 4.692c.46 0 .663-.211.921-.46l2.211-2.15 4.599 3.397c.848.467 1.457.227 1.668-.787l3.019-14.228c.309-1.239-.473-1.8-1.282-1.434z"/>
    </svg>
  );
  if (key === 'clawk' || key === 'clawnet') return (
    <svg {...strokeProps}><path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
  );
  if (key === 'clawstr') return (
    <svg {...strokeProps}><path d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"/></svg>
  );
  if (key === 'paylock') return (
    <svg {...strokeProps}><path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
  );
  if (key === 'agentmail') return (
    <svg {...strokeProps}><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
  );
  if (key === 'moltx' || key === 'moltbook') return (
    <svg {...strokeProps}><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
  );
  if (key === 'twitter' || key === 'x') return (
    <svg {...strokeProps} viewBox="0 0 24 24" fill="currentColor" stroke="none">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
    </svg>
  );
  if (key === 'discord') return (
    <svg {...strokeProps}><path d="M8.5 14.5A1.5 1.5 0 1010 13a1.5 1.5 0 00-1.5 1.5zm7 0A1.5 1.5 0 1017 13a1.5 1.5 0 00-1.5 1.5z"/><path d="M20.317 4.37a19.791 19.791 0 00-4.885-1.515.074.074 0 00-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.299 12.299 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03z"/></svg>
  );
  // Default globe icon
  return (
    <svg {...strokeProps}><path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"/></svg>
  );
}

function getScoreColor(score: number): string {
  if (score >= 80) return '#00d4aa';
  if (score >= 50) return '#f59e0b';
  return '#ef4444';
}

function getTrustLevel(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Highly Trusted', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' };
  if (score >= 51) return { label: 'Trusted', color: 'text-isnad-teal bg-isnad-teal/10 border-isnad-teal/20' };
  if (score >= 21) return { label: 'Building Trust', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' };
  return { label: 'Newcomer', color: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20' };
}

function daysSince(dateStr: string): number {
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24));
}

function ScoreBar({ label, score, delay = 0 }: { label: string; score: number; delay?: number }) {
  const color = getScoreColor(score);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-400">{label}</span>
        <span className="text-xs font-mono tabular-nums" style={{ color }}>{score}</span>
      </div>
      <div className="h-2 rounded-full bg-white/[0.06] overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ duration: 1.2, delay, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}

export default function AgentProfilePage() {
  const params = useParams();
  const agentId = params.id as string;

  const [agent, setAgent] = useState<AgentProfile | null>(null);
  const [trustV2, setTrustV2] = useState<TrustScoreV2Response | null>(null);
  const [badges, setBadges] = useState<BadgeRecord[]>([]);
  const [detail, setDetail] = useState<AgentDetailResponse | null>(null);
  const [trustReport, setTrustReport] = useState<TrustReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!agentId) return;
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        const [profile, v2, badgesResult, detailResult, reportResult] = await Promise.allSettled([
          getAgentProfile(agentId),
          getTrustScoreV2(agentId),
          getAgentBadges(agentId),
          getAgentDetail(agentId),
          getTrustReport(agentId),
        ]);

        if (cancelled) return;
        if (profile.status === 'fulfilled') setAgent(profile.value);
        else throw new Error('Agent not found');
        if (v2.status === 'fulfilled') setTrustV2(v2.value);
        if (badgesResult.status === 'fulfilled') setBadges(badgesResult.value);
        if (detailResult.status === 'fulfilled') setDetail(detailResult.value);
        if (reportResult.status === 'fulfilled') setTrustReport(reportResult.value);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [agentId]);

  if (loading) {
    return (
      <>
        <Navbar />
        <main className="min-h-screen pt-24 px-4 sm:px-6 max-w-5xl mx-auto pb-20">
          <div className="animate-pulse space-y-8">
            <div className="flex items-center gap-8">
              <div className="w-40 h-40 rounded-full bg-white/[0.06]" />
              <div className="space-y-4 flex-1">
                <div className="h-8 w-48 bg-white/[0.06] rounded" />
                <div className="h-4 w-32 bg-white/[0.04] rounded" />
                <div className="h-4 w-full bg-white/[0.04] rounded" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {[1,2,3,4].map(i => <div key={i} className="h-32 bg-white/[0.04] rounded-2xl" />)}
            </div>
          </div>
        </main>
      </>
    );
  }

  if (error || !agent) {
    return (
      <>
        <Navbar />
        <main className="min-h-screen pt-24 px-4 sm:px-6 max-w-5xl mx-auto pb-20 flex items-center justify-center">
          <div className="text-center">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-red-500/10 mb-6">
              <span className="text-3xl">😵</span>
            </div>
            <h2 className="text-xl font-semibold text-zinc-300 mb-2">Agent Not Found</h2>
            <p className="text-zinc-600 text-sm mb-6">{error || 'This agent does not exist.'}</p>
            <Link href="/explorer">
              <Button variant="ghost">← Back to Explorer</Button>
            </Link>
          </div>
        </main>
      </>
    );
  }

  const score = Math.round(agent.trust_score);
  const typeInfo = typeLabels[agent.agent_type] || typeLabels['autonomous'];
  const signals = trustV2?.signals;

  // Radar chart categories from v2 signals
  const radarCategories = signals ? [
    { label: 'Reputation', value: signals.platform_reputation.score },
    { label: 'Delivery', value: signals.delivery_track_record.score },
    { label: 'Identity', value: signals.identity_verification.score },
    { label: 'Consistency', value: signals.cross_platform_consistency.score },
  ] : [];

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-4 sm:px-6 max-w-5xl mx-auto pb-20">
        {/* Back link */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mb-8"
        >
          <Link href="/explorer" className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors font-mono">
            ← Explorer
          </Link>
        </motion.div>

        {/* Hero Section */}
        <motion.div
          className="relative bg-white/[0.02] backdrop-blur-xl border border-white/[0.06] rounded-3xl p-6 sm:p-8 md:p-12 mb-8 overflow-hidden"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          {/* Background gradient */}
          <div
            className="absolute inset-0 opacity-30 pointer-events-none"
            style={{
              background: `radial-gradient(ellipse at 20% 50%, ${getScoreColor(score)}10, transparent 60%)`,
            }}
          />

          <div className="relative flex flex-col md:flex-row items-center md:items-start gap-6 md:gap-10">
            {/* Avatar + Score grouped on mobile */}
            <div className="flex flex-row md:flex-col items-center gap-5 md:gap-6 shrink-0">
              {/* Avatar */}
              {agent.avatar_url ? (
                <img
                  src={agent.avatar_url}
                  alt={agent.name}
                  className="w-20 h-20 md:w-[120px] md:h-[120px] rounded-full object-cover border-2 border-white/[0.1] shadow-lg shadow-black/20"
                />
              ) : (
                <div className="w-20 h-20 md:w-[120px] md:h-[120px] rounded-full bg-white/[0.06] border-2 border-white/[0.1] flex items-center justify-center text-2xl md:text-4xl font-bold text-zinc-400 shadow-lg shadow-black/20">
                  {agent.name.charAt(0).toUpperCase()}
                </div>
              )}

              {/* Trust Score Ring */}
              <div className="hidden md:block">
                <TrustScoreRing score={score} size={140} strokeWidth={5} />
              </div>
              <div className="block md:hidden">
                <TrustScoreRing score={score} size={80} strokeWidth={4} />
              </div>
            </div>

            {/* Agent Info */}
            <div className="flex-1 text-center md:text-left min-w-0">
              <div className="flex flex-col sm:flex-row items-center md:items-start gap-2.5 mb-4">
                <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight text-white leading-tight">
                  {agent.name}
                </h1>
                <div className="flex items-center gap-2 flex-wrap justify-center md:justify-start">
                  <span className={`inline-flex items-center px-3 py-1 rounded-lg text-[11px] font-medium border ${typeInfo.color}`}>
                    {typeInfo.label}
                  </span>
                  {agent.is_certified && (
                    <span className="inline-flex items-center px-3 py-1 rounded-lg text-[11px] font-medium text-isnad-teal bg-isnad-teal/10 border border-isnad-teal/20">
                      ✓ Certified
                    </span>
                  )}
                  <TrustBadgeLarge score={score} />
                  {badges.filter(b => b.status === 'active').map(b => (
                    <span
                      key={b.id}
                      className="inline-flex items-center gap-1 px-3 py-1 rounded-lg text-[11px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20"
                      title={`Granted: ${b.granted_at ? new Date(b.granted_at).toLocaleDateString() : 'N/A'}${b.expires_at ? ` · Expires: ${new Date(b.expires_at).toLocaleDateString()}` : ''}`}
                    >
                      🛡️ isnad {b.badge_type.charAt(0).toUpperCase() + b.badge_type.slice(1)}
                    </span>
                  ))}
                  {badges.filter(b => b.status === 'pending').map(b => (
                    <span
                      key={b.id}
                      className="inline-flex items-center gap-1 px-3 py-1 rounded-lg text-[11px] font-medium text-yellow-400 bg-yellow-500/10 border border-yellow-500/20"
                    >
                      ⏳ {b.badge_type} (pending)
                    </span>
                  ))}
                </div>
              </div>

              {agent.description && (
                <p className="text-zinc-400 text-sm leading-relaxed mb-5 max-w-xl">
                  {agent.description}
                </p>
              )}

              {agent.offerings && (
                <div className="mb-5">
                  <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-mono block mb-1.5">Offerings</span>
                  <p className="text-zinc-300 text-sm leading-relaxed">{agent.offerings}</p>
                </div>
              )}

              {/* Meta row */}
              <div className="flex flex-wrap items-center justify-center md:justify-start gap-x-5 gap-y-1.5 text-[11px] text-zinc-600 font-mono pt-2 border-t border-white/[0.04]">
                <span title={agent.agent_id}>ID: {agent.agent_id.slice(0, 12)}…</span>
                <span>Registered: {new Date(agent.created_at).toLocaleDateString()}</span>
                {trustV2 && <span>Confidence: {trustV2.total_confidence.toFixed(2)}</span>}
              </div>
            </div>
          </div>
        </motion.div>

        {/* Activity Timeline + Security Info */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-8">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
            <Card>
              <h2 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
                Activity Timeline
              </h2>
              <div className="space-y-3 text-xs">
                <div className="flex justify-between"><span className="text-zinc-500">Registered</span><span className="text-zinc-300 font-mono">{new Date(agent.created_at).toLocaleDateString()}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Account Age</span><span className="text-zinc-300 font-mono">{daysSince(agent.created_at)} days</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Attestations</span><span className="text-zinc-300 font-mono">{detail?.attestation_count ?? 0}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Last Checked</span><span className="text-zinc-300 font-mono">{detail?.last_checked ? new Date(detail.last_checked).toLocaleDateString() : 'Never'}</span></div>
              </div>
            </Card>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <Card>
              <h2 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
                Security Info
              </h2>
              <div className="space-y-3 text-xs">
                <div className="flex justify-between"><span className="text-zinc-500">Key Fingerprint</span><span className="text-zinc-300 font-mono">{agent.public_key.slice(0, 16)}…</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Algorithm</span><span className="text-zinc-300 font-mono">Ed25519</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Key Created</span><span className="text-zinc-300 font-mono">{new Date(agent.created_at).toLocaleDateString()}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Signature</span><span className="text-zinc-300 font-mono">SHA-256</span></div>
              </div>
            </Card>
          </motion.div>
        </div>

        {/* Empty state + CTA when unscored */}
        {score === 0 && (
          <motion.div className="mb-8" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
            <Card className="text-center py-10 border-isnad-teal/10">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/[0.04] mb-5">
                <span className="text-3xl">🔍</span>
              </div>
              <h3 className="text-lg font-semibold text-zinc-300 mb-2">No Trust Data Yet</h3>
              <p className="text-zinc-500 text-sm max-w-md mx-auto mb-6">
                This agent hasn&apos;t been scored yet. Run a trust check to generate their first score.
              </p>
              <Link href={`/check/${agentId}`}>
                <Button size="lg">Run Trust Check →</Button>
              </Link>
            </Card>
          </motion.div>
        )}

        {/* Trust Breakdown + Radar */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Score Bars */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Card>
              <h2 className="text-sm font-semibold text-zinc-300 mb-6 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
                Trust Breakdown
              </h2>
              {signals ? (
                <div className="space-y-5">
                  <ScoreBar label="Platform Reputation" score={Math.round(signals.platform_reputation.score * 100)} delay={0.3} />
                  <ScoreBar label="Delivery Track Record" score={Math.round(signals.delivery_track_record.score * 100)} delay={0.4} />
                  <ScoreBar label="Identity Verification" score={Math.round(signals.identity_verification.score * 100)} delay={0.5} />
                  <ScoreBar label="Cross-Platform Consistency" score={Math.round(signals.cross_platform_consistency.score * 100)} delay={0.6} />
                </div>
              ) : (
                <p className="text-zinc-600 text-sm">No detailed trust data available yet.</p>
              )}
            </Card>
          </motion.div>

          {/* Radar Chart */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <Card>
              <h2 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
                Trust Radar
              </h2>
              {radarCategories.length > 0 ? (
                <RadarChart categories={radarCategories} size={260} />
              ) : (
                <div className="flex items-center justify-center h-[260px] text-zinc-600 text-sm">
                  Insufficient data for radar
                </div>
              )}
            </Card>
          </motion.div>
        </div>

        {/* Platforms */}
        {agent.platforms && agent.platforms.length > 0 && (
          <motion.div
            className="mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
          >
            <h2 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
              Connected Platforms
            </h2>
            <div className="flex flex-wrap gap-3">
              {agent.platforms.map((p, i) => {
                const Wrapper = p.url ? 'a' : 'div';
                const wrapperProps = p.url ? { href: p.url, target: '_blank', rel: 'noopener noreferrer' } : {};
                return (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.5 + i * 0.05 }}
                  >
                    <Wrapper {...wrapperProps} className={p.url ? 'block cursor-pointer group' : 'block'}>
                      <div className={`flex items-center gap-2.5 px-4 py-2.5 rounded-xl border transition-all duration-300 ${
                        p.url
                          ? 'border-white/[0.08] bg-white/[0.03] hover:border-isnad-teal/40 hover:bg-isnad-teal/[0.06] hover:shadow-[0_0_20px_-6px_rgba(0,212,170,0.2)]'
                          : 'border-white/[0.06] bg-white/[0.02]'
                      }`}>
                        <div className="text-zinc-500 group-hover:text-isnad-teal transition-colors">
                          <PlatformIcon name={p.name} className="w-[18px] h-[18px]" />
                        </div>
                        <span className="text-sm font-medium text-zinc-400 group-hover:text-zinc-200 transition-colors capitalize">
                          {p.name}
                        </span>
                        {p.url && (
                          <svg className="w-3 h-3 text-zinc-700 group-hover:text-isnad-teal/60 transition-colors ml-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5l15-15m0 0H8.25m11.25 0v11.25" />
                          </svg>
                        )}
                      </div>
                    </Wrapper>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* Capabilities */}
        {agent.capabilities && agent.capabilities.length > 0 && (
          <motion.div
            className="mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <Card>
              <h2 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
                Capabilities
              </h2>
              <div className="flex flex-wrap gap-2">
                {agent.capabilities.map((cap, i) => (
                  <span
                    key={i}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.04] text-zinc-400 border border-white/[0.06] hover:border-isnad-teal/20 hover:text-zinc-300 transition-all"
                  >
                    {cap}
                  </span>
                ))}
              </div>
            </Card>
          </motion.div>
        )}

        {/* Verification History (Trust Report) */}
        {trustReport && (
          <motion.div
            className="mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.55 }}
          >
            <Card>
              <h2 className="text-sm font-semibold text-zinc-300 mb-5 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
                Verification Report
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
                {Object.entries(trustReport.scores).map(([key, val]) => (
                  <div key={key} className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4 text-center">
                    <div className="text-2xl font-bold tabular-nums" style={{ color: getScoreColor(val.score) }}>
                      {val.score}
                    </div>
                    <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono mt-1">
                      {key}
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[11px] text-zinc-600 font-mono border-t border-white/[0.04] pt-3">
                <span>Overall: <span className="text-zinc-400">{trustReport.overall_score}</span></span>
                <span>Platforms: <span className="text-zinc-400">{trustReport.platform_count}</span></span>
                <span>Decay: <span className="text-zinc-400">{trustReport.decay_factor.toFixed(3)}</span></span>
                <span>Computed: <span className="text-zinc-400">{new Date(trustReport.computed_at).toLocaleString()}</span></span>
              </div>
            </Card>
          </motion.div>
        )}

        {/* Attestations */}
        {detail && detail.recent_attestations && detail.recent_attestations.length > 0 && (
          <motion.div
            className="mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
          >
            <Card>
              <h2 className="text-sm font-semibold text-zinc-300 mb-5 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
                Attestations ({detail.attestation_count})
              </h2>
              <div className="space-y-3">
                {detail.recent_attestations.map((att) => (
                  <div
                    key={att.attestation_id}
                    className="flex items-center justify-between bg-white/[0.03] border border-white/[0.06] rounded-xl px-4 py-3"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-full bg-white/[0.06] flex items-center justify-center text-xs font-semibold text-zinc-400 shrink-0">
                        {att.attester_name.charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <Link
                          href={`/agents/${att.attester_id}`}
                          className="text-sm font-medium text-zinc-300 hover:text-isnad-teal transition-colors truncate block"
                        >
                          {att.attester_name}
                        </Link>
                        <span className="text-[10px] text-zinc-600 font-mono">{att.scope}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-sm font-mono tabular-nums" style={{ color: getScoreColor(att.value * 100) }}>
                        {att.value.toFixed(1)}
                      </span>
                      <span className="text-[10px] text-zinc-600 font-mono">
                        {new Date(att.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </motion.div>
        )}

        {/* Contact & Public Key */}
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 gap-6"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
        >
          {agent.contact_email && (
            <Card>
              <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
                Contact
              </h2>
              <a
                href={`mailto:${agent.contact_email}`}
                className="text-sm text-isnad-teal hover:text-isnad-teal-light transition-colors"
              >
                {agent.contact_email}
              </a>
            </Card>
          )}

          <Card>
            <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
              Public Key
            </h2>
            <code className="text-[11px] text-zinc-500 font-mono break-all leading-relaxed">
              {agent.public_key}
            </code>
          </Card>
        </motion.div>
      </main>
    </>
  );
}
