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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

interface V3Dimension { raw: number; weighted: number; }
interface V3CheckResult {
  overall_score: number;
  confidence: number;
  tier: string;
  dimensions: {
    provenance: V3Dimension;
    track_record: V3Dimension;
    presence: V3Dimension;
    endorsements: V3Dimension;
    infra_integrity?: V3Dimension;
  };
}

const typeLabels: Record<string, { label: string; color: string }> = {
  autonomous: { label: 'Autonomous', color: 'text-purple-400 bg-purple-500/15 border-purple-500/20' },
  'tool-calling': { label: 'Tool-Calling', color: 'text-blue-400 bg-blue-500/15 border-blue-500/20' },
  'human-supervised': { label: 'Human-Supervised', color: 'text-amber-400 bg-amber-500/15 border-amber-500/20' },
};

// Platform categories with unified icons
type PlatformCategory = 'code' | 'marketplace' | 'social' | 'email';

function categorizePlatform(name: string): PlatformCategory {
  const key = name.toLowerCase();
  if (['github', 'gitlab', 'bitbucket', 'npm', 'pypi', 'huggingface'].includes(key)) return 'code';
  if (['ugig', 'paylock', 'acp', 'virtuals', 'bountycaster', 'immunefi'].includes(key)) return 'marketplace';
  if (['agentmail', 'email'].includes(key) || key.includes('mail')) return 'email';
  return 'social'; // clawk, clawstr, telegram, moltx, twitter, discord, etc.
}

const categoryMeta: Record<PlatformCategory, { label: string; color: string; iconPath: string }> = {
  code: {
    label: 'Code',
    color: 'text-violet-400 border-violet-500/20 bg-violet-500/[0.06]',
    iconPath: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4', // </>
  },
  marketplace: {
    label: 'Marketplaces',
    color: 'text-emerald-400 border-emerald-500/20 bg-emerald-500/[0.06]',
    iconPath: 'M13 10V3L4 14h7v7l9-11h-7z', // bolt
  },
  social: {
    label: 'Social',
    color: 'text-sky-400 border-sky-500/20 bg-sky-500/[0.06]',
    iconPath: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z', // people
  },
  email: {
    label: 'Contact',
    color: 'text-amber-400 border-amber-500/20 bg-amber-500/[0.06]',
    iconPath: 'M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z', // envelope
  },
};

function getScoreColor(score: number): string {
  if (score >= 80) return '#00d4aa';
  if (score >= 50) return '#f59e0b';
  return '#ef4444';
}

function getTrustLevel(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Certified', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' };
  if (score >= 60) return { label: 'Trusted', color: 'text-isnad-teal bg-isnad-teal/10 border-isnad-teal/20' };
  if (score >= 40) return { label: 'Established', color: 'text-blue-400 bg-blue-500/10 border-blue-500/20' };
  if (score >= 20) return { label: 'Emerging', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' };
  return { label: 'New', color: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20' };
}

function daysSince(dateStr: string): number {
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24));
}

function normalizePlatformUrl(name: string, rawUrl?: string): string | null {
  const raw = (rawUrl || '').trim();
  if (!raw) return null;

  if (/^https?:\/\//i.test(raw)) return raw;

  const key = name.toLowerCase();
  const handle = raw.replace(/^@/, '');

  if (key === 'clawstr') return `https://clawstr.com/${handle}`;
  if (key === 'clawk') return `https://clawk.ai/${handle}`;
  if (key === 'github') return `https://github.com/${handle}`;
  if (key === 'twitter' || key === 'x') return `https://x.com/${handle}`;
  if (key === 'telegram') return `https://t.me/${handle}`;
  if ((key === 'agentmail' || key === 'email') && handle.includes('@')) return `mailto:${handle}`;

  if (/^[\w.-]+\.[a-z]{2,}(\/.*)?$/i.test(raw)) return `https://${raw}`;
  return null;
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
  const [v3Check, setV3Check] = useState<V3CheckResult | null>(null);
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
        // Also fetch v3 check for proper dimensions
        try {
          const v3res = await fetch(`${API_BASE}/trust/${encodeURIComponent(agentId)}`);
          if (v3res.ok) { const v3data = await v3res.json(); if (!cancelled) setV3Check(v3data); }
        } catch {}

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
  const dims = v3Check?.dimensions;

  // Radar chart categories from v3 dimensions (preferred) or v2 signals (fallback)
  const radarCategories = dims ? [
    { label: 'Provenance', value: dims.provenance.raw },
    { label: 'Track Record', value: dims.track_record.raw },
    { label: 'Presence', value: dims.presence.raw },
    { label: 'Endorsements', value: dims.endorsements.raw },
    ...(dims.infra_integrity ? [{ label: 'Infrastructure', value: dims.infra_integrity.raw }] : []),
  ] : signals ? [
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
                {v3Check ? <span>Confidence: {v3Check.confidence.toFixed(2)}</span> : trustV2 && <span>Confidence: {trustV2.total_confidence.toFixed(2)}</span>}
                <a
                  href={`/badge/${encodeURIComponent(agent.name || agent.agent_id)}`}
                  className="ml-auto inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-[11px] font-medium text-isnad-teal bg-isnad-teal/10 border border-isnad-teal/20 hover:bg-isnad-teal/20 transition-colors"
                >
                  <svg width="12" height="12" viewBox="0 0 32 32" fill="none"><path d="M16 2L4 8v8c0 7 5 13 12 15 7-2 12-8 12-15V8L16 2z" stroke="currentColor" strokeWidth="2" fill="none"/><path d="M11 16l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  Get Badge
                </a>
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
              {dims ? (
                <div className="space-y-5">
                  <ScoreBar label="Provenance" score={Math.round(dims.provenance.raw * 100)} delay={0.3} />
                  <ScoreBar label="Track Record" score={Math.round(dims.track_record.raw * 100)} delay={0.4} />
                  <ScoreBar label="Presence" score={Math.round(dims.presence.raw * 100)} delay={0.5} />
                  <ScoreBar label="Endorsements" score={Math.round(dims.endorsements.raw * 100)} delay={0.6} />
                  {dims.infra_integrity && <ScoreBar label="Infrastructure" score={Math.round(dims.infra_integrity.raw * 100)} delay={0.7} />}
                </div>
              ) : signals ? (
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
        {agent.platforms && agent.platforms.length > 0 && (() => {
          // Group platforms by category
          const grouped: Record<PlatformCategory, typeof agent.platforms> = { code: [], marketplace: [], social: [], email: [] };
          agent.platforms.forEach(p => {
            const cat = (p as { category?: string }).category as PlatformCategory || categorizePlatform(p.name);
            if (!grouped[cat]) grouped[cat] = [];
            grouped[cat].push(p);
          });
          const activeCategories = (Object.keys(grouped) as PlatformCategory[]).filter(k => grouped[k].length > 0);

          return (
            <motion.div
              className="mb-8"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
            >
              <div className="mb-5 flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
                  Connected Platforms
                  <span className="text-[10px] text-zinc-600 font-mono ml-2">{agent.platforms.length} verified</span>
                </h2>
                <a
                  href={`/badge/${encodeURIComponent(agent.name || agent.agent_id)}`}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-medium text-isnad-teal bg-isnad-teal/10 border border-isnad-teal/20 hover:bg-isnad-teal/20 transition-colors"
                >
                  Get Badge
                </a>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {activeCategories.map((cat, ci) => {
                  const meta = categoryMeta[cat];
                  const platforms = grouped[cat];
                  return (
                    <motion.div
                      key={cat}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.45 + ci * 0.08 }}
                      className={`rounded-2xl border p-4 ${meta.color}`}
                    >
                      <div className="flex items-center gap-2 mb-3">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                          <path d={meta.iconPath} />
                        </svg>
                        <span className="text-xs font-semibold uppercase tracking-wider">{meta.label}</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {platforms.map((p, pi) => {
                          const href = normalizePlatformUrl(p.name, p.url);
                          const isLink = !!href;
                          const inner = (
                            <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                              isLink
                                ? 'bg-white/[0.06] text-zinc-300 hover:bg-white/[0.12] hover:text-white cursor-pointer'
                                : 'bg-white/[0.03] text-zinc-500'
                            }`}>
                              {p.name}
                              {isLink && (
                                <svg className="w-3 h-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5l15-15m0 0H8.25m11.25 0v11.25" />
                                </svg>
                              )}
                            </span>
                          );
                          return isLink ? (
                            <a key={pi} href={href} target="_blank" rel="noopener noreferrer">{inner}</a>
                          ) : (
                            <span key={pi}>{inner}</span>
                          );
                        })}
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </motion.div>
          );
        })()}

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
