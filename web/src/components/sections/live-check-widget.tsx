'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import TrustScoreRing from '@/components/trust-score-ring';

const mockCategories = [
  { label: 'Identity', value: 0.95 },
  { label: 'Attestation', value: 0.82 },
  { label: 'Behavioral', value: 0.91 },
  { label: 'Platform', value: 0.78 },
  { label: 'Transactions', value: 0.85 },
  { label: 'Security', value: 0.89 },
];

function barGradient(value: number): string {
  if (value > 0.85) return 'linear-gradient(90deg, #00d4aa, #00e6b8)';
  if (value > 0.7) return 'linear-gradient(90deg, #00d4aa, #6366f1)';
  return 'linear-gradient(90deg, #f59e0b, #f97316)';
}

export default function LiveCheckWidget() {
  const [query, setQuery] = useState('');
  const [checked, setChecked] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleCheck = () => {
    if (!query.trim()) return;
    setLoading(true);
    setChecked(false);
    setTimeout(() => {
      setLoading(false);
      setChecked(true);
    }, 1500);
  };

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
            placeholder="agent:example:gpt-4-assistant"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCheck()}
          />
          <Button onClick={handleCheck} disabled={loading} className="shrink-0">
            {loading ? (
              <span className="flex items-center gap-2">
                <svg
                  className="w-4 h-4 animate-spin"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="3"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Checking
              </span>
            ) : (
              'Check'
            )}
          </Button>
        </motion.div>

        <AnimatePresence>
          {checked && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.4 }}
              className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-8 flex flex-col md:flex-row items-center gap-10"
            >
              <TrustScoreRing score={87} size={180} label="Overall Trust" />
              <div className="flex-1 w-full space-y-4">
                {mockCategories.map((cat, i) => (
                  <div key={cat.label} className="space-y-1.5">
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">{cat.label}</span>
                      <span className="font-mono text-isnad-teal text-xs">
                        {cat.value.toFixed(2)}
                      </span>
                    </div>
                    <div className="h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
                      <motion.div
                        className="h-full rounded-full"
                        style={{ background: barGradient(cat.value) }}
                        initial={{ width: 0 }}
                        animate={{ width: `${cat.value * 100}%` }}
                        transition={{
                          duration: 0.8,
                          delay: 0.2 + i * 0.1,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}
