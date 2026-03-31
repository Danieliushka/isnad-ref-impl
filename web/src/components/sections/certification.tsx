import AnimatedSection from './animated-section';
import { Card } from '@/components/ui/card';

const BADGE_LEVELS = [
  { name: 'UNTESTED', color: 'text-zinc-500', bg: 'bg-zinc-500/10', desc: 'No red-team assessment' },
  { name: 'TESTED', color: 'text-blue-400', bg: 'bg-blue-400/10', desc: 'Tier 1 completed' },
  { name: 'RESILIENT', color: 'text-yellow-400', bg: 'bg-yellow-400/10', desc: 'Tier 1-2, ≥80% blocked' },
  { name: 'CERTIFIED', color: 'text-emerald-400', bg: 'bg-emerald-400/10', desc: 'Tier 1-3, ≥90% blocked' },
  { name: 'VERIFIED', color: 'text-isnad-teal', bg: 'bg-isnad-teal/10', desc: 'Tier 1-3, 100% blocked' },
];

const TIERS = [
  { tier: 1, vectors: 10, price: '$25', desc: 'Prompt injection, social engineering, role confusion' },
  { tier: 2, vectors: 15, price: '$50', desc: 'Multi-step attacks, document injection, config manipulation' },
  { tier: 3, vectors: 12, price: '$75', desc: 'Chain attacks, tool-use boundary, meta-layer exploitation' },
];

export default function Certification() {
  return (
    <AnimatedSection id="certification" className="py-24 px-4 sm:px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-isnad-teal/60 mb-3 block">
            Security
          </span>
          <h2 className="font-heading text-3xl md:text-4xl font-bold tracking-tight mb-3">
            Red-Team Certification
          </h2>
          <p className="text-zinc-500 text-sm max-w-xl mx-auto">
            Prove your agent&apos;s resilience with adversarial testing. 37 attack vectors across 3 tiers — from basic injection to meta-layer exploitation.
          </p>
        </div>

        {/* Badge Levels */}
        <div className="flex flex-wrap justify-center gap-3 mb-12">
          {BADGE_LEVELS.map((b) => (
            <div key={b.name} className={`${b.bg} rounded-full px-4 py-1.5 flex items-center gap-2`}>
              <span className={`text-xs font-mono font-bold ${b.color}`}>{b.name}</span>
              <span className="text-[10px] text-zinc-500">{b.desc}</span>
            </div>
          ))}
        </div>

        {/* Tiers */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
          {TIERS.map((t) => (
            <Card key={t.tier}>
              <div className="flex items-baseline justify-between mb-2">
                <h3 className="text-sm font-semibold text-zinc-300">Tier {t.tier}</h3>
                <span className="text-isnad-teal font-mono text-sm font-bold">{t.price}</span>
              </div>
              <p className="text-[10px] text-zinc-500 mb-3">{t.vectors} attack vectors</p>
              <p className="text-xs text-zinc-400">{t.desc}</p>
            </Card>
          ))}
        </div>

        {/* Full Battery */}
        <Card>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-zinc-300 mb-1">Full Battery — All 3 Tiers</h3>
              <p className="text-xs text-zinc-500">37 vectors. Quarterly re-certification at 50% discount.</p>
            </div>
            <span className="text-isnad-teal font-mono text-lg font-bold">$125</span>
          </div>
        </Card>

        <div className="mt-8 text-center">
          <p className="text-zinc-600 text-xs">
            Powered by Stark Red Team × isnad. Results feed directly into trust scores.
          </p>
        </div>
      </div>
    </AnimatedSection>
  );
}
