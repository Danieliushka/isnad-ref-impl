'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import TrustScoreRing from '@/components/trust-score-ring';
import RadarChart from '@/components/radar-chart';
import { getAgentProfile, getTrustScoreV2, getAgentBadges, getAgentDetail, getTrustReport, type AgentProfile, type TrustScoreV2Response, type BadgeRecord, type AgentDetailResponse, type TrustReport } from '@/lib/api';

const typeLabels: Record<string, { label: string; color: string }> = {
  autonomous: { label: 'Autonomous', color: 'text-purple-400 bg-purple-500/15 border-purple-500/20' },
  'tool-calling': { label: 'Tool-Calling', color: 'text-blue-400 bg-blue-500/15 border-blue-500/20' },
  'human-supervised': { label: 'Human-Supervised', color: 'text-amber-400 bg-amber-500/15 border-amber-500/20' },
};

const platformIcons: Record<string, string> = {
  github: '⚡', ugig: '🔗', twitter: '𝕏', linkedin: '💼',
  npm: '📦', pypi: '🐍', huggingface: '🤗', discord: '💬',
};

function getScoreColor(score: number): string {
  if (score >= 80) return '#00d4aa';
  if (score >= 50) return '#f59e0b';
  return '#ef4444';
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
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {agent.platforms.map((p, i) => {
                const key = p.name.toLowerCase();
                const icon = platformIcons[key] || '🌐';
                const Wrapper = p.url ? 'a' : 'div';
                const wrapperProps = p.url ? { href: p.url, target: '_blank', rel: 'noopener noreferrer' } : {};
                return (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5 + i * 0.08 }}
                  >
                    <Wrapper {...wrapperProps} className={p.url ? 'block cursor-pointer' : 'block'}>
                      <Card className={`flex items-center gap-4 transition-all duration-300 ${p.url ? 'hover:border-isnad-teal/30 hover:scale-[1.02] hover:bg-white/[0.04]' : ''}`}>
                        <div className="w-10 h-10 rounded-xl bg-white/[0.06] flex items-center justify-center text-lg">
                          {icon}
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-sm font-medium text-zinc-300 capitalize">{p.name}</span>
                        </div>
                        {p.url && (
                          <svg className="w-4 h-4 text-zinc-600 group-hover:text-isnad-teal transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path d="M7 17l9.2-9.2M17 17V7H7" />
                          </svg>
                        )}
                      </Card>
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
