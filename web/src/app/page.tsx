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
import TrustBadgeShowcase from '@/components/sections/trust-badge-showcase';
import TrustedBy from '@/components/sections/trusted-by';

/* ── How It Works ── */
const steps = [
  {
    num: '01',
    title: 'Submit',
    desc: 'Enter an agent ID, name, or public key. No registration required — just paste and go.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
        <rect x="8" y="6" width="24" height="28" rx="3" stroke="#00d4aa" strokeWidth="1.5" />
        <path d="M14 16h12M14 22h8" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M20 30l4-4h-8l4 4z" fill="#00d4aa" opacity="0.4" />
      </svg>
    ),
  },
  {
    num: '02',
    title: 'Analyze',
    desc: '36 modules scan identity, attestation chains, behavioral patterns, platform presence, and security posture.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
        <circle cx="20" cy="20" r="14" stroke="#00d4aa" strokeWidth="1.5" strokeDasharray="4 3" />
        <circle cx="20" cy="20" r="8" stroke="#00d4aa" strokeWidth="1.5" />
        <circle cx="20" cy="20" r="2" fill="#00d4aa" />
        <line x1="20" y1="6" x2="20" y2="12" stroke="#00d4aa" strokeWidth="1.5" />
        <line x1="34" y1="20" x2="28" y2="20" stroke="#00d4aa" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    num: '03',
    title: 'Certify',
    desc: 'Get a gradient trust score (0–100) with full category breakdown. Agents scoring ≥80 earn certification.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
        <path
          d="M20 4L6 12v10c0 8 6 14 14 16 8-2 14-8 14-16V12L20 4z"
          stroke="#00d4aa"
          strokeWidth="1.5"
          fill="none"
        />
        <path
          d="M14 20l4 4 8-8"
          stroke="#00d4aa"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
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
        <rect x="6" y="14" width="20" height="14" rx="2" stroke="#00d4aa" strokeWidth="1.5" />
        <path d="M11 14V10a5 5 0 0110 0v4" stroke="#00d4aa" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    title: 'Trust Scoring',
    desc: 'Gradient 0\u20131 scores based on relationship graphs, activity rhythm, and behavioral fingerprints.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <circle cx="16" cy="16" r="12" stroke="#00d4aa" strokeWidth="1.5" />
        <path d="M16 8v8l6 4" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    title: 'Attestation Chains',
    desc: 'Verifiable provenance through linked cryptographic attestations with temporal decay.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <circle cx="8" cy="16" r="4" stroke="#00d4aa" strokeWidth="1.5" />
        <circle cx="24" cy="16" r="4" stroke="#00d4aa" strokeWidth="1.5" />
        <line x1="12" y1="16" x2="20" y2="16" stroke="#00d4aa" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    title: 'Takeover Detection',
    desc: 'Behavioral anomaly scoring detects compromised or impersonated agents.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <path d="M16 4l2 6h6l-5 4 2 6-5-4-5 4 2-6-5-4h6l2-6z" stroke="#00d4aa" strokeWidth="1.5" fill="none" />
      </svg>
    ),
  },
  {
    title: 'API & SDK',
    desc: 'REST endpoints, Python SDK, and CLI for every trust verification workflow.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <path d="M10 10l-6 6 6 6M22 10l6 6-6 6" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="18" y1="8" x2="14" y2="24" stroke="#00d4aa" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    title: 'Multi-Platform',
    desc: 'Works across ugig, Clawk, AgentMail, and any custom agent platform.',
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <rect x="4" y="8" width="24" height="16" rx="3" stroke="#00d4aa" strokeWidth="1.5" />
        <line x1="4" y1="14" x2="28" y2="14" stroke="#00d4aa" strokeWidth="1.5" />
      </svg>
    ),
  },
];

/* ── Explorer Mock Data ── */
const agents = [
  { name: 'gpt-4o', score: 92, status: 'Certified', checked: '2 min ago' },
  { name: 'claude-3-5', score: 89, status: 'Certified', checked: '5 min ago' },
  { name: 'gendolf', score: 87, status: 'Certified', checked: '15 min ago' },
  { name: 'trading-bot-v2', score: 67, status: 'Pending', checked: '1 hr ago' },
  { name: 'deepseek-v3', score: 44, status: 'Failed', checked: '3 hr ago' },
];

export default function HomePage() {
  return (
    <main className="min-h-screen">
      <Navbar />

      {/* Hero */}
      <section id="hero">
        <HeroSection />
      </section>

      {/* Stats Bar */}
      <section id="stats">
        <StatsBar />
      </section>

      {/* Trusted By */}
      <TrustedBy />

      <div className="glow-divider max-w-4xl mx-auto" />

      {/* Register CTA */}
      <AnimatedSection id="register-cta" className="py-24 px-4 sm:px-6">
        <div className="max-w-3xl mx-auto">
          <Card className="p-6 sm:p-8 md:p-12 text-center border-isnad-teal/10">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-isnad-teal/10 border border-isnad-teal/20 mb-6">
              <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
                <circle cx="16" cy="12" r="5" stroke="#00d4aa" strokeWidth="1.5" />
                <path d="M6 26c0-5.523 4.477-10 10-10s10 4.477 10 10" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" />
                <path d="M22 8l4 4M26 8l-4 4" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </div>
            <h2 className="font-heading text-2xl md:text-3xl font-bold tracking-tight mb-3">
              Register Your Agent
            </h2>
            <p className="text-zinc-500 text-sm mb-8 max-w-md mx-auto leading-relaxed">
              Create a cryptographic identity in seconds. Get an Ed25519 keypair and start receiving attestations from the network.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Link href="/register">
                <Button size="lg">Register Now →</Button>
              </Link>
              <Link href="/docs">
                <Button variant="secondary" size="lg">Learn More</Button>
              </Link>
            </div>
          </Card>
        </div>
      </AnimatedSection>

      <div className="glow-divider max-w-4xl mx-auto" />

      {/* Live Check Widget */}
      <section id="live-check">
        <LiveCheckWidget />
      </section>

      <div className="glow-divider max-w-4xl mx-auto" />

      {/* How It Works */}
      <AnimatedSection id="how-it-works" className="py-24 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-isnad-teal/60 mb-3 block">
              Process
            </span>
            <h2 className="font-heading text-3xl md:text-4xl font-bold tracking-tight">
              How It Works
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {steps.map((step, i) => (
              <AnimatedSection
                key={step.title}
                delay={i * 0.15}
              >
                <Card className="h-full text-center">
                  <div className="flex justify-center mb-5 opacity-50">
                    {step.icon}
                  </div>
                  <div className="text-[10px] font-mono text-isnad-teal/60 tracking-[0.2em] uppercase mb-3">
                    Step {step.num}
                  </div>
                  <h3 className="text-lg font-semibold mb-2 text-zinc-200">
                    {step.title}
                  </h3>
                  <p className="text-zinc-500 text-sm leading-relaxed">
                    {step.desc}
                  </p>
                </Card>
              </AnimatedSection>
            ))}
          </div>
        </div>
      </AnimatedSection>

      <div className="glow-divider max-w-4xl mx-auto" />

      {/* Features Grid */}
      <AnimatedSection id="features" className="py-24 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-isnad-teal/60 mb-3 block">
              Capabilities
            </span>
            <h2 className="font-heading text-3xl md:text-4xl font-bold tracking-tight">
              Features
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {features.map((f, i) => (
              <AnimatedSection key={f.title} delay={i * 0.08}>
                <Card className="h-full">
                  <div className="mb-4 opacity-50">{f.icon}</div>
                  <h3 className="text-base font-semibold mb-2 text-zinc-200">
                    {f.title}
                  </h3>
                  <p className="text-zinc-500 text-sm leading-relaxed">
                    {f.desc}
                  </p>
                </Card>
              </AnimatedSection>
            ))}
          </div>
        </div>
      </AnimatedSection>

      <div className="glow-divider max-w-4xl mx-auto" />

      {/* Trust Explorer Preview */}
      <AnimatedSection id="explorer" className="py-24 px-4 sm:px-6">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-isnad-teal/60 mb-3 block">
              Network
            </span>
            <h2 className="font-heading text-3xl md:text-4xl font-bold tracking-tight mb-3">
              Trust Explorer
            </h2>
            <p className="text-zinc-500 text-sm">
              Live agent trust scores, updated in real time
            </p>
          </div>
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/[0.06]">
                    <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">
                      Agent
                    </th>
                    <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">
                      Score
                    </th>
                    <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">
                      Status
                    </th>
                    <th className="text-right px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">
                      Last Checked
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((a) => (
                    <tr
                      key={a.name}
                      className="border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="px-6 py-4 font-mono text-sm text-isnad-teal">
                        {a.name}
                      </td>
                      <td className="px-6 py-4">
                        <Badge score={a.score}>{a.score}</Badge>
                      </td>
                      <td className="px-6 py-4 text-zinc-400 text-xs">{a.status}</td>
                      <td className="px-6 py-4 text-right text-zinc-600 text-xs font-mono">
                        {a.checked}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-6 py-4 border-t border-white/[0.04] text-center">
              <Link
                href="/explorer"
                className="text-isnad-teal/70 hover:text-isnad-teal text-sm font-medium transition-colors"
              >
                View all agents →
              </Link>
            </div>
          </div>
        </div>
      </AnimatedSection>

      <div className="glow-divider max-w-4xl mx-auto" />

      {/* Trust Badge Showcase */}
      <TrustBadgeShowcase />

      <div className="glow-divider max-w-4xl mx-auto" />

      {/* API Section */}
      <ApiTabs />

      {/* CTA */}
      <AnimatedSection id="cta" className="py-24 sm:py-32 px-4 sm:px-6">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="font-heading text-3xl md:text-5xl font-bold tracking-tight mb-6">
            Start Verifying Agents
            <br />
            <span className="bg-gradient-to-r from-isnad-teal via-isnad-teal-light to-accent bg-clip-text text-transparent">
              Today
            </span>
          </h2>
          <p className="text-zinc-500 mb-10 text-sm">
            Free tier available. No credit card required.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/register">
              <Button size="lg">Register Your Agent →</Button>
            </Link>
            <Link href="/check">
              <Button variant="secondary" size="lg">
                Check an Agent
              </Button>
            </Link>
          </div>
        </div>
      </AnimatedSection>

      {/* Footer */}
      <footer
        id="footer"
        className="border-t border-white/[0.04] py-12 sm:py-16 px-4 sm:px-6"
      >
        <div className="max-w-5xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-10">
            {/* Brand */}
            <div className="md:col-span-1">
              <div className="flex items-center gap-1.5 mb-3">
                <span className="text-lg font-bold text-white">isnad</span>
                <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
              </div>
              <p className="text-xs text-zinc-600 leading-relaxed">
                Trust infrastructure for the AI agent economy. Verify, certify, and build trust.
              </p>
            </div>
            {/* Product */}
            <div>
              <h4 className="text-[10px] font-mono tracking-[0.15em] uppercase text-zinc-500 mb-3">Product</h4>
              <nav className="flex flex-col gap-2 text-sm text-zinc-600">
                <Link href="/check" className="hover:text-zinc-400 transition-colors">Check Agent</Link>
                <Link href="/explorer" className="hover:text-zinc-400 transition-colors">Explorer</Link>
                <Link href="/register" className="hover:text-zinc-400 transition-colors">Register</Link>
              </nav>
            </div>
            {/* Developers */}
            <div>
              <h4 className="text-[10px] font-mono tracking-[0.15em] uppercase text-zinc-500 mb-3">Developers</h4>
              <nav className="flex flex-col gap-2 text-sm text-zinc-600">
                <Link href="/docs" className="hover:text-zinc-400 transition-colors">Documentation</Link>
                <a href="https://github.com/Danieliushka/isnad-ref-impl" target="_blank" rel="noopener noreferrer" className="hover:text-zinc-400 transition-colors">GitHub</a>
                <Link href="/docs" className="hover:text-zinc-400 transition-colors">API Reference</Link>
              </nav>
            </div>
            {/* Protocol */}
            <div>
              <h4 className="text-[10px] font-mono tracking-[0.15em] uppercase text-zinc-500 mb-3">Protocol</h4>
              <nav className="flex flex-col gap-2 text-sm text-zinc-600">
                <span className="text-zinc-700">v1.0 — Active</span>
                <span className="text-zinc-700">1000+ tests passing</span>
                <span className="text-zinc-700">Open source</span>
              </nav>
            </div>
          </div>
          <div className="border-t border-white/[0.04] pt-6 flex flex-col sm:flex-row items-center justify-between gap-3">
            <p className="text-xs text-zinc-700 font-mono">
              © 2025 isnad. Built with cryptography, not trust.
            </p>
            <p className="text-[10px] text-zinc-800 font-mono">
              Ed25519 · SHA-256 · AsyncPG
            </p>
          </div>
        </div>
      </footer>
    </main>
  );
}
