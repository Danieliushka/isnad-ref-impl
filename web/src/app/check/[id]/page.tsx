'use client';

import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import TrustScoreRing from '@/components/trust-score-ring';
import RadarChart from '@/components/radar-chart';
import {
  getAgentById,
  getGrade,
  mockAgents,
  mockAttestations,
  defaultAttestations,
  mockRiskFlags,
  type ExplorerAgent,
  type AttestationEntry,
} from '@/lib/mock-data';
import { useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { useState } from 'react';

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.12 } },
};
const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

const categoryLabels: Record<string, string> = {
  identity: 'Identity Verification',
  attestation: 'Attestation Chain',
  behavioral: 'Behavioral Analysis',
  platform: 'Platform Presence',
  transactions: 'Transaction History',
  security: 'Security Posture',
};

// Score breakdown weights for the trust algorithm
const scoreBreakdown = [
  { key: 'relationship_graph', label: 'Relationship Graph', weight: 35 },
  { key: 'activity_rhythm', label: 'Activity Rhythm', weight: 25 },
  { key: 'topic_drift', label: 'Topic Drift', weight: 20 },
  { key: 'writing_fingerprint', label: 'Writing Fingerprint', weight: 20 },
];

function barColor(value: number): string {
  if (value >= 0.8) return 'bg-isnad-teal';
  if (value >= 0.6) return 'bg-yellow-500';
  return 'bg-red-500';
}

function barGlow(value: number): string {
  if (value >= 0.8) return 'shadow-isnad-teal/30';
  if (value >= 0.6) return 'shadow-yellow-500/30';
  return 'shadow-red-500/30';
}

function statusBadgeVariant(status: string): 'success' | 'warning' | 'danger' {
  if (status === 'certified') return 'success';
  if (status === 'pending') return 'warning';
  return 'danger';
}

function statusLabel(status: string): string {
  if (status === 'certified') return 'Certified';
  if (status === 'pending') return 'Pending';
  return 'Failed';
}

export default function TrustReportPage() {
  const params = useParams();
  const id = typeof params.id === 'string' ? decodeURIComponent(params.id) : 'unknown';

  const agentData: ExplorerAgent = getAgentById(id) ?? mockAgents[0];
  const { agent, score, status } = agentData;
  const grade = getGrade(score.overall);
  const attestations: AttestationEntry[] = mockAttestations[id] ?? defaultAttestations;
  const riskFlags: string[] = mockRiskFlags[id] ?? [];

  const [showEmbed, setShowEmbed] = useState(false);
  const [copied, setCopied] = useState(false);

  const radarCategories = (Object.entries(score.categories) as [string, number][]).map(([key, value]) => ({
    label: categoryLabels[key] ?? key,
    value,
  }));

  // Generate simulated breakdown scores based on overall score
  const breakdownScores = scoreBreakdown.map((b) => ({
    ...b,
    score: Math.min(1, Math.max(0.1, (score.overall / 100) + (Math.random() * 0.2 - 0.1))),
  }));

  const embedCode = `<img src="https://isnad.network/badge/${id}" alt="${agent.name} trust badge" />`;

  function copyEmbed() {
    navigator.clipboard.writeText(embedCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function shareReport() {
    if (navigator.share) {
      navigator.share({ title: `${agent.name} Trust Report`, url: window.location.href });
    } else {
      navigator.clipboard.writeText(window.location.href);
    }
  }

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-6 max-w-5xl mx-auto pb-20">
        <motion.div variants={container} initial="hidden" animate="show">
          {/* Header */}
          <motion.div variants={item} className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-8">
            <div>
              <h1 className="font-heading text-3xl md:text-4xl font-bold tracking-tight">{agent.name}</h1>
              <p className="font-mono text-isnad-teal text-sm mt-1">{agent.id}</p>
              <p className="font-mono text-zinc-600 text-xs mt-0.5">{agent.publicKey}</p>
              <p className="text-zinc-500 text-sm mt-2">Checked just now</p>
            </div>
            <Badge variant={statusBadgeVariant(status)}>{statusLabel(status)}</Badge>
          </motion.div>

          {/* Score + Radar */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <motion.div variants={item}>
              <Card className="flex flex-col items-center justify-center py-10">
                <TrustScoreRing score={score.overall} size={220} />
                <div className="mt-4 text-center">
                  <span className="font-heading text-2xl font-bold text-zinc-300">{grade}</span>
                  <p className="text-sm text-zinc-500 mt-1">
                    Confidence:{' '}
                    <span className={score.confidence === 'high' ? 'text-isnad-teal' : score.confidence === 'medium' ? 'text-yellow-400' : 'text-red-400'}>
                      {score.confidence}
                    </span>
                  </p>
                  <p className="text-[10px] font-mono text-zinc-600 mt-2 tracking-[0.15em] uppercase">
                    {attestations.length} attestations
                  </p>
                </div>
              </Card>
            </motion.div>

            <motion.div variants={item}>
              <Card className="flex items-center justify-center py-10">
                <RadarChart categories={radarCategories} size={280} />
              </Card>
            </motion.div>
          </div>

          {/* Score Breakdown (algorithm weights) */}
          <motion.div variants={item}>
            <Card className="mb-4">
              <h2 className="font-heading text-lg font-semibold mb-1 text-zinc-200">Score Breakdown</h2>
              <p className="text-[10px] font-mono tracking-[0.15em] uppercase text-zinc-600 mb-6">Algorithm weight distribution</p>
              <div className="space-y-4">
                {breakdownScores.map((b) => (
                  <div key={b.key}>
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-medium text-zinc-300">{b.label}</span>
                        <span className="text-[10px] font-mono text-zinc-600 tracking-wide">{b.weight}%</span>
                      </div>
                      <span className="text-sm font-mono text-isnad-teal tabular-nums">{(b.score * 100).toFixed(0)}</span>
                    </div>
                    <div className="h-2 bg-white/[0.04] rounded-full overflow-hidden">
                      <motion.div
                        className={`h-full rounded-full shadow-sm ${barColor(b.score)} ${barGlow(b.score)}`}
                        initial={{ width: 0 }}
                        animate={{ width: `${b.score * 100}%` }}
                        transition={{ duration: 1, delay: 0.3, ease: 'easeOut' }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </motion.div>

          {/* Category Breakdown */}
          <motion.div variants={item}>
            <Card className="mb-4">
              <h2 className="font-heading text-lg font-semibold mb-6 text-zinc-200">Category Breakdown</h2>
              <div className="space-y-4">
                {(Object.entries(score.categories) as [string, number][]).map(([key, value]) => (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm font-medium text-zinc-300">{categoryLabels[key]}</span>
                      <span className="text-sm font-mono text-zinc-400 tabular-nums">{(value * 100).toFixed(0)}</span>
                    </div>
                    <div className="h-2 bg-white/[0.04] rounded-full overflow-hidden">
                      <motion.div
                        className={`h-full rounded-full shadow-sm ${barColor(value)} ${barGlow(value)}`}
                        initial={{ width: 0 }}
                        animate={{ width: `${value * 100}%` }}
                        transition={{ duration: 1, delay: 0.3, ease: 'easeOut' }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </motion.div>

          {/* Risk Flags */}
          <motion.div variants={item}>
            <Card className={`mb-4 ${riskFlags.length > 0 ? 'border-yellow-500/20' : 'border-isnad-teal/20'}`}>
              <h2 className="font-heading text-lg font-semibold mb-3 text-zinc-200">
                {riskFlags.length > 0 ? '⚠ Risk Flags' : '✓ Risk Assessment'}
              </h2>
              {riskFlags.length > 0 ? (
                <ul className="space-y-2">
                  {riskFlags.map((flag: string, i: number) => (
                    <li key={i} className="text-sm text-zinc-400 flex items-start gap-2">
                      <span className="text-yellow-400 mt-0.5 shrink-0">•</span>
                      {flag}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-isnad-teal">No risk flags detected</p>
              )}
            </Card>
          </motion.div>

          {/* Attestation History */}
          <motion.div variants={item}>
            <Card className="mb-4">
              <h2 className="font-heading text-lg font-semibold mb-6 text-zinc-200">Attestation History</h2>
              <div className="relative">
                <div className="absolute left-3 top-2 bottom-2 w-px bg-white/[0.06]" />
                <div className="space-y-6">
                  {attestations.map((att: AttestationEntry, i: number) => (
                    <motion.div
                      key={i}
                      className="flex items-start gap-4 pl-8 relative"
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.8 + i * 0.1 }}
                    >
                      <div className={`absolute left-1.5 top-1.5 w-3 h-3 rounded-full border-2 ${att.score >= 80 ? 'border-isnad-teal bg-isnad-teal/20' : att.score >= 60 ? 'border-yellow-500 bg-yellow-500/20' : 'border-red-500 bg-red-500/20'}`} />
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="text-sm font-medium text-zinc-200">{att.task}</span>
                            <span className="text-xs text-zinc-500 ml-2">by {att.witness}</span>
                          </div>
                          <Badge score={att.score}>{att.score}</Badge>
                        </div>
                        <p className="text-xs text-zinc-600 font-mono mt-1">
                          {new Date(att.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                        </p>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            </Card>
          </motion.div>

          {/* Actions */}
          <motion.div variants={item}>
            <Card className="mb-8">
              <h2 className="font-heading text-lg font-semibold mb-4 text-zinc-200">Actions</h2>
              <div className="flex flex-wrap gap-3">
                <Button variant="primary" onClick={() => setShowEmbed(!showEmbed)}>
                  Get Badge
                </Button>
                <Button variant="secondary" onClick={shareReport}>
                  Share Report
                </Button>
                <Button variant="ghost" onClick={() => window.location.reload()}>
                  Re-check
                </Button>
              </div>

              {showEmbed && (
                <motion.div
                  className="mt-4 p-4 bg-white/[0.02] rounded-xl border border-white/[0.06]"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                >
                  <p className="text-[10px] font-mono tracking-[0.15em] uppercase text-zinc-500 mb-2">Embed Badge</p>
                  <code className="block text-sm text-isnad-teal font-mono break-all bg-white/[0.02] p-3 rounded-lg border border-white/[0.04]">
                    {embedCode}
                  </code>
                  <Button size="sm" variant="ghost" className="mt-2" onClick={copyEmbed}>
                    {copied ? '✓ Copied' : 'Copy'}
                  </Button>
                </motion.div>
              )}
            </Card>
          </motion.div>

          {/* Footer */}
          <motion.div variants={item} className="text-center text-xs text-zinc-600 font-mono">
            isnad v0.3.0 · {new Date().toLocaleDateString()}
          </motion.div>
        </motion.div>
      </main>
    </>
  );
}
