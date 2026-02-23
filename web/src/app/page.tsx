import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import HeroSection from '@/components/sections/hero-section';
import LiveCheckWidget from '@/components/sections/live-check-widget';
import StatsBar from '@/components/sections/stats-bar';
import AnimatedSection from '@/components/sections/animated-section';
import ApiTabs from '@/components/sections/api-tabs';

/* ── How It Works ── */
const steps = [
  {
    title: 'Submit Agent ID',
    desc: 'Provide an agent identifier — DID, public key, or platform handle.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
        <circle cx="18" cy="18" r="10" stroke="#00d4aa" strokeWidth="2" />
        <line x1="25" y1="25" x2="35" y2="35" stroke="#00d4aa" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    title: '36-Module Analysis',
    desc: 'Cryptographic, behavioral, and attestation checks across 6 categories.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
        <rect x="4" y="20" width="6" height="16" rx="1" fill="#00d4aa" opacity="0.5" />
        <rect x="13" y="12" width="6" height="24" rx="1" fill="#00d4aa" opacity="0.7" />
        <rect x="22" y="16" width="6" height="20" rx="1" fill="#00d4aa" opacity="0.6" />
        <rect x="31" y="6" width="6" height="30" rx="1" fill="#00d4aa" />
      </svg>
    ),
  },
  {
    title: 'Get Certified',
    desc: 'Receive a verifiable trust score and optional on-chain certification.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
        <path d="M20 4L6 12v10c0 8 6 14 14 16 8-2 14-8 14-16V12L20 4z" stroke="#00d4aa" strokeWidth="2" fill="none" />
        <path d="M14 20l4 4 8-8" stroke="#00d4aa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

/* ── Features ── */
const features = [
  {
    title: 'Cryptographic Identity',
    desc: 'Ed25519 signatures ensure unforgeable agent identities.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <rect x="6" y="14" width="20" height="14" rx="2" stroke="#00d4aa" strokeWidth="2" />
        <path d="M11 14V10a5 5 0 0110 0v4" stroke="#00d4aa" strokeWidth="2" />
      </svg>
    ),
  },
  {
    title: 'Trust Scoring',
    desc: 'Gradient 0–1 scores, not binary yes/no judgments.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <circle cx="16" cy="16" r="12" stroke="#00d4aa" strokeWidth="2" />
        <path d="M16 8v8l6 4" stroke="#00d4aa" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    title: 'Attestation Chains',
    desc: 'Verifiable provenance through linked cryptographic attestations.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <circle cx="8" cy="16" r="4" stroke="#00d4aa" strokeWidth="2" />
        <circle cx="24" cy="16" r="4" stroke="#00d4aa" strokeWidth="2" />
        <line x1="12" y1="16" x2="20" y2="16" stroke="#00d4aa" strokeWidth="2" />
      </svg>
    ),
  },
  {
    title: 'Takeover Detection',
    desc: 'Behavioral anomaly scoring detects compromised agents.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <path d="M16 4l2 6h6l-5 4 2 6-5-4-5 4 2-6-5-4h6l2-6z" stroke="#00d4aa" strokeWidth="2" fill="none" />
      </svg>
    ),
  },
  {
    title: 'API Access',
    desc: 'REST endpoints, Python SDK, and CLI for every workflow.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <path d="M10 10l-6 6 6 6M22 10l6 6-6 6" stroke="#00d4aa" strokeWidth="2" strokeLinecap="round" />
        <line x1="18" y1="8" x2="14" y2="24" stroke="#00d4aa" strokeWidth="2" />
      </svg>
    ),
  },
  {
    title: 'ACP Bridge',
    desc: 'Native Agent Commerce Protocol integration for payments.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <rect x="4" y="8" width="24" height="16" rx="3" stroke="#00d4aa" strokeWidth="2" />
        <line x1="4" y1="14" x2="28" y2="14" stroke="#00d4aa" strokeWidth="2" />
      </svg>
    ),
  },
];

/* ── Explorer Mock Data ── */
const agents = [
  { name: 'gpt-4-assistant', score: 92, status: 'Certified', checked: '2 min ago' },
  { name: 'claude-3-opus', score: 88, status: 'Certified', checked: '5 min ago' },
  { name: 'trading-bot-v2', score: 67, status: 'Under Review', checked: '12 min ago' },
  { name: 'data-scraper-x', score: 41, status: 'Flagged', checked: '1 hr ago' },
  { name: 'support-agent-7', score: 85, status: 'Certified', checked: '3 hr ago' },
];

export default function HomePage() {
  return (
    <main className="min-h-screen">
      <Navbar />

      {/* Hero */}
      <HeroSection />

      {/* Live Check Widget */}
      <LiveCheckWidget />

      {/* Stats Bar */}
      <StatsBar />

      {/* How It Works */}
      <AnimatedSection className="py-24 px-6">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-16">How It Works</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
            {steps.map((step, i) => (
              <AnimatedSection key={step.title} delay={i * 0.15} className="text-center">
                <div className="flex justify-center mb-4">{step.icon}</div>
                <div className="text-xs font-mono text-isnad-teal mb-2">Step {i + 1}</div>
                <h3 className="text-xl font-semibold mb-2">{step.title}</h3>
                <p className="text-zinc-400 text-sm">{step.desc}</p>
              </AnimatedSection>
            ))}
          </div>
        </div>
      </AnimatedSection>

      {/* Features Grid */}
      <AnimatedSection className="py-24 px-6">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-16">Features</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((f, i) => (
              <AnimatedSection key={f.title} delay={i * 0.1}>
                <Card className="h-full">
                  <div className="mb-4">{f.icon}</div>
                  <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
                  <p className="text-zinc-400 text-sm">{f.desc}</p>
                </Card>
              </AnimatedSection>
            ))}
          </div>
        </div>
      </AnimatedSection>

      {/* Trust Explorer Preview */}
      <AnimatedSection className="py-24 px-6">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">Trust Explorer</h2>
          <p className="text-zinc-400 text-center mb-10">Live agent trust scores, updated in real time</p>
          <div className="bg-[var(--card-bg)] border border-[var(--card-border)] rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--card-border)] text-zinc-400">
                    <th className="text-left px-6 py-4 font-medium">Agent</th>
                    <th className="text-left px-6 py-4 font-medium">Score</th>
                    <th className="text-left px-6 py-4 font-medium">Status</th>
                    <th className="text-right px-6 py-4 font-medium">Last Checked</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((a) => (
                    <tr key={a.name} className="border-b border-[var(--card-border)] last:border-0 hover:bg-white/5 transition-colors">
                      <td className="px-6 py-4 font-mono text-isnad-teal">{a.name}</td>
                      <td className="px-6 py-4"><Badge score={a.score}>{a.score}</Badge></td>
                      <td className="px-6 py-4">{a.status}</td>
                      <td className="px-6 py-4 text-right text-zinc-500">{a.checked}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-6 py-4 border-t border-[var(--card-border)] text-center">
              <Link href="/explorer" className="text-isnad-teal hover:underline text-sm font-medium">
                View all →
              </Link>
            </div>
          </div>
        </div>
      </AnimatedSection>

      {/* API Section */}
      <ApiTabs />

      {/* CTA */}
      <AnimatedSection className="py-24 px-6">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">Start Verifying Agents Today</h2>
          <p className="text-zinc-400 mb-8">Free tier available. No credit card required.</p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/check">
              <Button size="lg">Get API Key</Button>
            </Link>
            <Link href="/docs">
              <Button variant="secondary" size="lg">Read Docs</Button>
            </Link>
          </div>
        </div>
      </AnimatedSection>

      {/* Footer */}
      <footer className="border-t border-[var(--card-border)] py-12 px-6">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="text-xl font-bold text-isnad-teal">isnad</div>
          <nav className="flex gap-6 text-sm text-zinc-400">
            <a href="https://github.com/Danieliushka/isnad-ref-impl" target="_blank" rel="noopener noreferrer" className="hover:text-isnad-teal transition-colors">GitHub</a>
            <Link href="/docs" className="hover:text-isnad-teal transition-colors">Docs</Link>
            <Link href="/check" className="hover:text-isnad-teal transition-colors">API</Link>
            <Link href="/explorer" className="hover:text-isnad-teal transition-colors">Explorer</Link>
          </nav>
          <p className="text-xs text-zinc-600 italic">Built with cryptography, not trust.</p>
        </div>
      </footer>
    </main>
  );
}
