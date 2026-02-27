'use client';

import AnimatedSection from './animated-section';

const platforms = [
  { name: 'ugig', desc: 'Agent marketplace' },
  { name: 'Clawk', desc: 'Agent platform' },
  { name: 'AgentMail', desc: 'Agent communication' },
  { name: 'OpenClaw', desc: 'Agent runtime' },
];

export default function TrustedBy() {
  return (
    <AnimatedSection className="py-16 px-4 sm:px-6">
      <div className="max-w-4xl mx-auto text-center">
        <p className="text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-600 mb-8">
          Integrated with leading agent platforms
        </p>
        <div className="flex flex-wrap items-center justify-center gap-8 md:gap-12">
          {platforms.map((p) => (
            <div key={p.name} className="group flex flex-col items-center gap-1">
              <span className="text-lg font-semibold text-zinc-600 group-hover:text-zinc-400 transition-colors">
                {p.name}
              </span>
              <span className="text-[10px] text-zinc-700 font-mono">
                {p.desc}
              </span>
            </div>
          ))}
        </div>
      </div>
    </AnimatedSection>
  );
}
