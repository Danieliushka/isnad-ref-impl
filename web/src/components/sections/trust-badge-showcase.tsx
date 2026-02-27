'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import AnimatedSection from './animated-section';

const badgeStyles = [
  {
    name: 'Shield',
    preview: (score: number) => (
      <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-isnad-teal/20 to-isnad-teal/5 border border-isnad-teal/30">
        <svg width="20" height="20" viewBox="0 0 32 32" fill="none">
          <path d="M16 2L4 8v8c0 7 5 13 12 15 7-2 12-8 12-15V8L16 2z" stroke="#00d4aa" strokeWidth="1.5" fill="none" />
          <path d="M11 16l3 3 7-7" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-sm font-semibold text-isnad-teal">isnad verified</span>
        <span className="text-xs font-mono text-zinc-400">{score}/100</span>
      </div>
    ),
    code: (agentId: string) =>
      `<a href="https://isnad.site/agents/${agentId}">
  <img src="https://isnad.site/api/v1/badge/${agentId}?style=shield" alt="isnad trust badge" />
</a>`,
  },
  {
    name: 'Minimal',
    preview: (score: number) => (
      <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-zinc-900 border border-white/10">
        <span className="w-2 h-2 rounded-full bg-isnad-teal" />
        <span className="text-xs font-mono text-zinc-300">isnad {score}</span>
      </div>
    ),
    code: (agentId: string) =>
      `<a href="https://isnad.site/agents/${agentId}">
  <img src="https://isnad.site/api/v1/badge/${agentId}?style=minimal" alt="isnad score" />
</a>`,
  },
  {
    name: 'Full',
    preview: (score: number) => (
      <div className="inline-flex items-center gap-3 px-5 py-3 rounded-xl bg-gradient-to-r from-zinc-900 to-zinc-800 border border-white/10">
        <div className="relative w-10 h-10">
          <svg viewBox="0 0 36 36" className="w-10 h-10 -rotate-90">
            <circle cx="18" cy="18" r="15" fill="none" stroke="#27272a" strokeWidth="3" />
            <circle
              cx="18" cy="18" r="15" fill="none" stroke="#00d4aa" strokeWidth="3"
              strokeDasharray={`${(score / 100) * 94.2} 94.2`}
              strokeLinecap="round"
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-isnad-teal font-mono">
            {score}
          </span>
        </div>
        <div>
          <div className="text-xs font-semibold text-zinc-200">isnad certified</div>
          <div className="text-[10px] text-zinc-500 font-mono">Trust Score {score}/100</div>
        </div>
      </div>
    ),
    code: (agentId: string) =>
      `<a href="https://isnad.site/agents/${agentId}">
  <img src="https://isnad.site/api/v1/badge/${agentId}?style=full" alt="isnad trust badge" />
</a>`,
  },
];

export default function TrustBadgeShowcase() {
  const [activeStyle, setActiveStyle] = useState(0);
  const [copied, setCopied] = useState(false);
  const demoScore = 87;
  const demoAgent = 'gendolf';

  const handleCopy = () => {
    navigator.clipboard.writeText(badgeStyles[activeStyle].code(demoAgent));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <AnimatedSection id="badges" className="py-24 px-4 sm:px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-isnad-teal/60 mb-3 block">
            Showcase
          </span>
          <h2 className="font-heading text-3xl md:text-4xl font-bold tracking-tight mb-3">
            Trust Badges
          </h2>
          <p className="text-zinc-500 text-sm max-w-lg mx-auto">
            Embed verifiable trust badges on your agent&apos;s profile, README, or website. Real-time scores, cryptographically backed.
          </p>
        </div>

        <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl overflow-hidden">
          {/* Badge style tabs */}
          <div className="flex border-b border-white/[0.06]">
            {badgeStyles.map((style, i) => (
              <button
                key={style.name}
                onClick={() => setActiveStyle(i)}
                className={`flex-1 px-4 py-3 text-xs font-mono tracking-wide transition-all cursor-pointer ${
                  activeStyle === i
                    ? 'text-isnad-teal bg-white/[0.03] border-b-2 border-isnad-teal'
                    : 'text-zinc-600 hover:text-zinc-400'
                }`}
              >
                {style.name}
              </button>
            ))}
          </div>

          {/* Preview */}
          <div className="p-8 flex items-center justify-center min-h-[120px] bg-[#0a0b0f]">
            <motion.div
              key={activeStyle}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.2 }}
            >
              {badgeStyles[activeStyle].preview(demoScore)}
            </motion.div>
          </div>

          {/* Code */}
          <div className="border-t border-white/[0.06] p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-mono text-zinc-600 tracking-wider uppercase">
                Embed Code
              </span>
              <button
                onClick={handleCopy}
                className="text-xs font-mono text-isnad-teal/70 hover:text-isnad-teal transition-colors cursor-pointer"
              >
                {copied ? '✓ Copied' : 'Copy'}
              </button>
            </div>
            <pre className="bg-[#0c0d12] rounded-lg p-4 overflow-x-auto">
              <code className="text-xs font-mono text-zinc-500 leading-relaxed">
                {badgeStyles[activeStyle].code(demoAgent)}
              </code>
            </pre>
          </div>
        </div>
      </div>
    </AnimatedSection>
  );
}
