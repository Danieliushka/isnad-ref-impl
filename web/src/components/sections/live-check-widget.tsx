'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import TrustScoreRing from '@/components/trust-score-ring';
import { getTrustScoreV2, type TrustScoreV2Response } from '@/lib/api';

const signalLabels: Record<string, string> = {
  platform_reputation: 'Platform Reputation',
  delivery_track_record: 'Delivery Track Record',
  identity_verification: 'Identity Verification',
  cross_platform_consistency: 'Cross-Platform Consistency',
};

function barGradient(value: number): string {
  if (value > 0.7) return 'linear-gradient(90deg, #00d4aa, #00e6b8)';
  if (value > 0.4) return 'linear-gradient(90deg, #f59e0b, #00d4aa)';
  return 'linear-gradient(90deg, #ef4444, #f59e0b)';
}

export default function LiveCheckWidget() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TrustScoreV2Response | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCheck = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const data = await getTrustScoreV2(query.trim());
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Check failed');
    } finally {
      setLoading(false);
    }
  };

  const signals = result
    ? Object.entries(result.signals).map(([key, sig]) => ({
        key,
        label: signalLabels[key] ?? key,
        score: sig.score,
        weight: sig.weight,
        confidence: sig.confidence,
      }))
    : [];

  return (
    <section className="py-24 px-6">
      <div className="max-w-4xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-10"
        >
          <h2 className="font-heading text-3xl md:text-4xl font-bold tracking-tight mb-4">
            Try It Now
          </h2>
          <p className="text-zinc-500">
            Enter any agent ID to see a live trust evaluation
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="flex gap-3 max-w-xl mx-auto mb-10"
        >
          <Input
            placeholder="gendolf"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCheck()}
          />
          <Button onClick={handleCheck} disabled={loading} className="shrink-0">
            {loading ? (
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Checking
              </span>
            ) : (
              'Check'
            )}
          </Button>
        </motion.div>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-center text-red-400 text-sm mb-6"
            >
              {error}
            </motion.div>
          )}

          {result && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.4 }}
              className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-8"
            >
              <div className="flex flex-col md:flex-row items-center gap-10">
                <div className="flex flex-col items-center">
                  <TrustScoreRing score={Math.round(result.trust_score * 100)} size={180} label="Overall Trust" />
                  <p className="text-[10px] font-mono text-zinc-600 mt-3 tracking-wide">
                    v{result.version} · confidence {(result.total_confidence * 100).toFixed(0)}%
                  </p>
                  {result.platforms_checked.length > 0 && (
                    <p className="text-[10px] font-mono text-zinc-600 mt-1">
                      {result.platforms_checked.join(' · ')}
                    </p>
                  )}
                </div>

                <div className="flex-1 w-full space-y-5">
                  {signals.map((sig, i) => (
                    <div key={sig.key} className="space-y-1.5">
                      <div className="flex justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span className="text-zinc-400">{sig.label}</span>
                          <span className="text-[10px] font-mono text-zinc-600">{(sig.weight * 100).toFixed(0)}%</span>
                        </div>
                        <span className="font-mono text-isnad-teal text-xs tabular-nums">
                          {(sig.score * 100).toFixed(0)}
                        </span>
                      </div>
                      <div className="h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
                        <motion.div
                          className="h-full rounded-full"
                          style={{ background: barGradient(sig.score) }}
                          initial={{ width: 0 }}
                          animate={{ width: `${sig.score * 100}%` }}
                          transition={{ duration: 0.8, delay: 0.2 + i * 0.1 }}
                        />
                      </div>
                      {sig.confidence < 0.5 && (
                        <p className="text-[10px] text-zinc-600">Low confidence — insufficient data</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}
