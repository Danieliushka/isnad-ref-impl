'use client';

import AnimatedSection from './animated-section';

const platforms = [
  { name: 'ugig', desc: 'Agent marketplace', url: 'https://ugig.net' },
  { name: 'Clawk', desc: 'Social platform', url: 'https://clawk.ai' },
  { name: 'PayLock', desc: 'Agent escrow', url: 'https://paylock.xyz' },
  { name: 'CoinPay', desc: 'Crypto payments', url: 'https://coinpayportal.com' },
  { name: 'OpenClaw', desc: 'Agent runtime', url: 'https://openclaw.ai' },
  { name: 'AgentMail', desc: 'Agent email', url: 'https://agentmail.to' },
  { name: 'Moltlaunch', desc: 'Agent launchpad', url: 'https://moltlaunch.com' },
  { name: 'GitHub', desc: 'Code & repos', url: 'https://github.com' },
  { name: 'Virtuals ACP', desc: 'Agent commerce', url: 'https://app.virtuals.io/acp' },
  { name: 'Code4rena', desc: 'Security audits', url: 'https://code4rena.com' },
  { name: 'Immunefi', desc: 'Bug bounties', url: 'https://immunefi.com' },
  { name: 'Moltbook', desc: 'Agent social', url: 'https://moltbook.ai' },
];

// Duplicate for seamless infinite scroll
const doubled = [...platforms, ...platforms];

export default function TrustedBy() {
  return (
    <AnimatedSection className="py-16 px-4 sm:px-6">
      <div className="max-w-5xl mx-auto text-center">
        <p className="text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-600 mb-8">
          Integrated with leading agent platforms
        </p>
        <div className="relative overflow-hidden">
          {/* Fade edges */}
          <div className="absolute left-0 top-0 bottom-0 w-20 bg-gradient-to-r from-[#050507] to-transparent z-10 pointer-events-none" />
          <div className="absolute right-0 top-0 bottom-0 w-20 bg-gradient-to-l from-[#050507] to-transparent z-10 pointer-events-none" />
          
          <div className="flex items-center gap-10 animate-scroll">
            {doubled.map((p, i) => (
              <a
                key={`${p.name}-${i}`}
                href={p.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex flex-col items-center gap-1 shrink-0 min-w-[100px]"
              >
                <span className="text-lg font-semibold text-zinc-600 group-hover:text-zinc-300 transition-colors whitespace-nowrap">
                  {p.name}
                </span>
                <span className="text-[10px] text-zinc-700 group-hover:text-zinc-500 font-mono whitespace-nowrap transition-colors">
                  {p.desc}
                </span>
              </a>
            ))}
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes scroll {
          0% {
            transform: translateX(0);
          }
          100% {
            transform: translateX(-50%);
          }
        }
        .animate-scroll {
          animation: scroll 30s linear infinite;
        }
        .animate-scroll:hover {
          animation-play-state: paused;
        }
      `}</style>
    </AnimatedSection>
  );
}
