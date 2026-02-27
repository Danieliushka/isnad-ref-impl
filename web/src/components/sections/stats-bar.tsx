'use client';

import { motion, useInView, animate } from 'framer-motion';
import { useRef, useEffect, useState } from 'react';

function AnimatedCounter({
  target,
  suffix = '',
}: {
  target: number;
  suffix?: string;
}) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!isInView || target === 0) return;
    const ctrl = animate(0, target, {
      duration: 2,
      ease: 'easeOut',
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return () => ctrl.stop();
  }, [isInView, target]);

  return (
    <span
      ref={ref}
      className="text-4xl md:text-5xl font-bold text-isnad-teal font-mono tabular-nums"
    >
      {display.toLocaleString()}
      {suffix}
    </span>
  );
}

interface StatsData {
  tests: number;
  modules: number;
  agents: number;
  checks: number;
}

const FALLBACK: StatsData = { tests: 1029, modules: 36, agents: 8, checks: 0 };

export default function StatsBar() {
  const [data, setData] = useState<StatsData>(FALLBACK);

  useEffect(() => {
    async function load() {
      try {
        const [healthRes, agentsRes, statsRes] = await Promise.all([
          fetch('/api/v1/health', { next: { revalidate: 0 } } as RequestInit),
          fetch('/api/v1/agents?limit=1', { next: { revalidate: 0 } } as RequestInit),
          fetch('/api/v1/stats', { next: { revalidate: 0 } } as RequestInit).catch(() => null),
        ]);
        const health = await healthRes.json();
        const agents = await agentsRes.json();
        const stats = statsRes ? await statsRes.json() : {};
        setData({
          tests: health.tests ?? FALLBACK.tests,
          modules: health.modules ?? FALLBACK.modules,
          agents: agents.total ?? FALLBACK.agents,
          checks: stats.agents_checked ?? FALLBACK.checks,
        });
      } catch {
        // keep fallback
      }
    }
    load();
  }, []);

  const stats = [
    { target: data.tests, suffix: '+', label: 'Tests Passing' },
    { target: data.modules, suffix: '', label: 'Scoring Dimensions' },
    { target: data.agents, suffix: '', label: 'Registered Agents' },
    { target: data.checks, suffix: '', label: 'Trust Checks' },
  ];

  return (
    <section className="py-20 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-8 md:p-12">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-10 md:gap-0 text-center">
            {stats.map((s, i) => (
              <motion.div
                key={s.label}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.15 }}
                className={i > 0 ? 'md:border-l md:border-white/[0.06]' : ''}
              >
                <AnimatedCounter target={s.target} suffix={s.suffix} />
                <p className="mt-3 text-zinc-500 text-sm tracking-wide">
                  {s.label}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
