'use client';

import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import TrustScoreRing from '@/components/trust-score-ring';
import RadarChart from '@/components/radar-chart';
import { getTrustScoreV2, type TrustScoreV2Response, type SignalDetail } from '@/lib/api';
import { useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.12 } },
};
const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

const signalLabels: Record<string, string> = {
  platform_reputation: 'Platform Reputation',
  delivery_track_record: 'Delivery Track Record',
  identity_verification: 'Identity Verification',
  cross_platform_consistency: 'Cross-Platform Consistency',
};

const signalDescriptions: Record<string, string> = {
  platform_reputation: 'Ratings & reviews across marketplaces',
  delivery_track_record: 'Job completion rate, disputes, delivery history',
  identity_verification: 'Profile completeness, account age, verified links',
  cross_platform_consistency: 'Presence across multiple platforms, username consistency',
};

function barColor(value: number): string {
  if (value >= 0.7) return 'bg-isnad-teal';
  if (value >= 0.4) return 'bg-yellow-500';
  return 'bg-red-500';
}

function barGlow(value: number): string {
  if (value >= 0.7) return 'shadow-isnad-teal/30';
  if (value >= 0.4) return 'shadow-yellow-500/30';
  return 'shadow-red-500/30';
}

function getGrade(score: number): string {
  if (score >= 90) return 'A+';
  if (score >= 80) return 'A';
  if (score >= 70) return 'B+';
  if (score >= 60) return 'B';
  if (score >= 50) return 'C';
  if (score >= 35) return 'D';
  return 'F';
}

function getConfidenceLevel(c: number): 'high' | 'medium' | 'low' {
  if (c >= 0.7) return 'high';
  if (c >= 0.4) return 'medium';
  return 'low';
}

export default function TrustReportPage() {
  const params = useParams();
  const id = typeof params.id === 'string' ? decodeURIComponent(params.id) : 'unknown';

  const [data, setData] = useState<TrustScoreV2Response | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEmbed, setShowEmbed] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getTrustScoreV2(id)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <>
        <Navbar />
        <main className="min-h-screen pt-24 px-6 max-w-5xl mx-auto pb-20 flex items-center justify-center">
          <div className="text-center">
            <svg className="w-8 h-8 animate-spin text-isnad-teal mx-auto mb-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <p className="text-zinc-500 font-mono text-sm">Fetching trust data for {id}...</p>
          </div>
        </main>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <Navbar />
        <main className="min-h-screen pt-24 px-6 max-w-5xl mx-auto pb-20 flex items-center justify-center">
          <Card className="text-center p-10">
            <h2 className="font-heading text-2xl font-bold text-red-400 mb-2">Check Failed</h2>
            <p className="text-zinc-500">{error || 'Unknown error'}</p>
            <Button variant="secondary" className="mt-4" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </Card>
        </main>
      </>
    );
  }

  const scorePercent = Math.round(data.trust_score * 100);
  const grade = getGrade(scorePercent);
  const confidence = getConfidenceLevel(data.total_confidence);

  const signals = Object.entries(data.signals) as [string, SignalDetail][];
  const radarCategories = signals.map(([key, sig]) => ({
    label: signalLabels[key] ?? key,
    value: sig.score,
  }));

  const embedCode = `<img src="https://isnad.network/badge/${id}" alt="${id} trust badge" />`;

  function copyEmbed() {
    navigator.clipboard.writeText(embedCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function shareReport() {
    if (navigator.share) {
      navigator.share({ title: `${id} Trust Report`, url: window.location.href });
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
              <h1 className="font-heading text-3xl md:text-4xl font-bold tracking-tight">{id}</h1>
              <p className="text-zinc-500 text-sm mt-2">
                Checked just now · v{data.version}
              </p>
              {data.platforms_checked.length > 0 && (
                <p className="text-[10px] font-mono text-zinc-600 mt-1 tracking-wide">
                  Platforms: {data.platforms_checked.join(' · ')}
                </p>
              )}
            </div>
            <Badge variant={scorePercent >= 60 ? 'success' : scorePercent >= 35 ? 'warning' : 'danger'}>
              {grade}
            </Badge>
          </motion.div>

          {/* Score + Radar */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <motion.div variants={item}>
              <Card className="flex flex-col items-center justify-center py-10">
                <TrustScoreRing score={scorePercent} size={220} />
                <div className="mt-4 text-center">
                  <span className="font-heading text-2xl font-bold text-zinc-300">{grade}</span>
                  <p className="text-sm text-zinc-500 mt-1">
                    Confidence:{' '}
                    <span className={confidence === 'high' ? 'text-isnad-teal' : confidence === 'medium' ? 'text-yellow-400' : 'text-red-400'}>
                      {confidence}
                    </span>
                    <span className="text-zinc-600 ml-1 font-mono text-xs">({(data.total_confidence * 100).toFixed(0)}%)</span>
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

          {/* Signal Breakdown */}
          <motion.div variants={item}>
            <Card className="mb-4">
              <h2 className="font-heading text-lg font-semibold mb-1 text-zinc-200">Trust Score v2</h2>
              <p className="text-[10px] font-mono tracking-[0.15em] uppercase text-zinc-600 mb-6">Real platform data · Verifiable signals</p>
              <div className="space-y-5">
                {signals.map(([key, sig]) => (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-medium text-zinc-300">{signalLabels[key]}</span>
                        <span className="text-[10px] font-mono text-zinc-600 tracking-wide">{(sig.weight * 100).toFixed(0)}%</span>
                      </div>
                      <span className="text-sm font-mono text-isnad-teal tabular-nums">{(sig.score * 100).toFixed(0)}</span>
                    </div>
                    <p className="text-[11px] text-zinc-600 mb-1.5">{signalDescriptions[key]}</p>
                    <div className="h-2 bg-white/[0.04] rounded-full overflow-hidden">
                      <motion.div
                        className={`h-full rounded-full shadow-sm ${barColor(sig.score)} ${barGlow(sig.score)}`}
                        initial={{ width: 0 }}
                        animate={{ width: `${sig.score * 100}%` }}
                        transition={{ duration: 1, delay: 0.3, ease: 'easeOut' }}
                      />
                    </div>
                    <div className="flex items-center gap-4 mt-1">
                      <span className="text-[10px] font-mono text-zinc-700">
                        confidence: {(sig.confidence * 100).toFixed(0)}%
                      </span>
                      {Object.keys(sig.evidence).length > 0 && (
                        <span className="text-[10px] font-mono text-zinc-700">
                          evidence: {Object.keys(sig.evidence).join(', ')}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
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
            isnad v0.4.0 · TrustScore v{data.version} · {new Date().toLocaleDateString()}
          </motion.div>
        </motion.div>
      </main>
    </>
  );
}
