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
          <h2 className="text-3xl md:text-4xl font-bold mb-4">Try It Now</h2>
          <p className="text-zinc-400">Enter any agent ID to see a live trust evaluation</p>
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
            {loading ? 'Checking…' : 'Check'}
          </Button>
        </motion.div>

        <AnimatePresence>
          {checked && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.5 }}
              className="bg-[var(--card-bg)] border border-[var(--card-border)] rounded-2xl p-8 flex flex-col md:flex-row items-center gap-8"
            >
              <TrustScoreRing score={87} size={180} label="Overall Trust" />
              <div className="flex-1 w-full space-y-3">
                {mockCategories.map((cat, i) => (
                  <div key={cat.label} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-400">{cat.label}</span>
                      <span className="font-mono text-isnad-teal">{cat.value.toFixed(2)}</span>
                    </div>
                    <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-isnad-teal rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${cat.value * 100}%` }}
                        transition={{ duration: 0.8, delay: 0.2 + i * 0.1 }}
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
