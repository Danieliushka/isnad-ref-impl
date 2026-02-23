'use client';

import { motion, useInView, useMotionValue, useTransform, animate } from 'framer-motion';
import { useRef, useEffect, useState } from 'react';

function AnimatedCounter({ target, suffix = '' }: { target: number; suffix?: string }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!isInView) return;
    const ctrl = animate(0, target, {
      duration: 2,
      ease: 'easeOut',
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return () => ctrl.stop();
  }, [isInView, target]);

  return (
    <span ref={ref} className="text-4xl md:text-5xl font-bold text-isnad-teal font-mono">
      {display.toLocaleString()}{suffix}
    </span>
  );
}

const stats = [
  { target: 1000, suffix: '+', label: 'Tests Passing' },
  { target: 36, suffix: '', label: 'Modules' },
  { target: 6, suffix: '', label: 'Trust Categories' },
];

export default function StatsBar() {
  return (
    <section className="py-16 px-6 border-y border-[var(--card-border)]">
      <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-10 text-center">
        {stats.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: i * 0.15 }}
          >
            <AnimatedCounter target={s.target} suffix={s.suffix} />
            <p className="mt-2 text-zinc-400 text-sm">{s.label}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
