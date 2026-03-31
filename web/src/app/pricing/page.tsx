import type { Metadata } from 'next';
import Link from 'next/link';
import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export const metadata: Metadata = {
  title: 'Pricing — isnad',
  description: 'Simple, transparent pricing for AI agent trust verification. Free tier included.',
};

const tiers = [
  {
    name: 'Free',
    price: '$0',
    period: '/month',
    description: 'For individual developers and early-stage teams validating a single agent surface.',
    checks: '50',
    features: [
      '50 trust checks/month',
      'Public agent profile',
      'Trust score summary',
      'REST API access',
      'Community support',
    ],
    cta: 'Start Free',
    href: '/register',
    highlighted: false,
  },
  {
    name: 'Pro',
    price: '$29',
    period: '/month',
    description: 'For production teams embedding trust checks, badges, and richer evidence flows.',
    checks: '10,000',
    features: [
      '10,000 trust checks/month',
      'Expanded score breakdown',
      'Attestation chain visibility',
      'Higher rate limits',
      'Webhook notifications',
      'Priority support',
    ],
    cta: 'Talk About Pro',
    href: 'mailto:daniel@isnad.site?subject=isnad%20Pro',
    highlighted: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    description: 'For networks, registries, or marketplaces that need private deployment and custom controls.',
    checks: 'Unlimited',
    features: [
      'Unlimited trust checks',
      'Dedicated infrastructure',
      'Custom scoring modules',
      'Private deployment options',
      'SLA planning',
      'Custom integrations',
    ],
    cta: 'Contact Sales',
    href: 'mailto:daniel@isnad.site?subject=isnad%20Enterprise',
    highlighted: false,
  },
];

const included = [
  'Public profiles and badge surfaces',
  'API documentation and examples',
  'Cryptographic identity primitives',
  'Human support while the platform is in pilot',
];

const faqs = [
  {
    question: 'How do trust checks work now?',
    answer:
      'Public profile checks are served from the latest stored trust result. Expensive recomputation is intentionally restricted after the P0 hardening pass.',
  },
  {
    question: 'When should I move beyond the free tier?',
    answer:
      'Move up when you need higher monthly volume, richer evidence detail, or platform-level support for integrating trust flows into your own product.',
  },
  {
    question: 'Do all plans include the public badge flow?',
    answer:
      'Yes. The public trust surface is part of the product story across tiers, with higher plans focused on scale, support, and deeper operational use.',
  },
  {
    question: 'Are these limits final?',
    answer:
      'The platform is still being hardened in production. This page reflects the current public packaging, but canonical monetization policy should still be finalized in the next iteration.',
  },
];

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0 mt-0.5">
      <path d="M4 8l3 3 5-5" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TierAction({ href, cta, highlighted }: { href: string; cta: string; highlighted: boolean }) {
  if (href.startsWith('mailto:')) {
    return (
      <a href={href} className="block">
        <Button variant={highlighted ? 'primary' : 'secondary'} size="md" className="w-full">
          {cta}
        </Button>
      </a>
    );
  }

  return (
    <Link href={href}>
      <Button variant={highlighted ? 'primary' : 'secondary'} size="md" className="w-full">
        {cta}
      </Button>
    </Link>
  );
}

export default function PricingPage() {
  return (
    <main className="min-h-screen">
      <Navbar />

      <section className="relative overflow-hidden px-4 pt-32 pb-24 sm:px-6">
        <div className="absolute inset-0 hero-mesh opacity-70" />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(5,5,7,0.25),rgba(5,5,7,0.96))]" />

        <div className="relative max-w-6xl mx-auto">
          <div className="max-w-3xl text-center mx-auto mb-14">
            <span className="mb-4 inline-flex items-center gap-2 rounded-full border border-isnad-teal/15 bg-isnad-teal/10 px-4 py-1.5 text-[11px] font-mono uppercase tracking-[0.28em] text-isnad-teal/80">
              pilot pricing
            </span>
            <h1 className="font-heading text-4xl md:text-6xl font-bold tracking-tight mb-4">
              Pricing for teams shipping
              <span className="bg-gradient-to-r from-isnad-teal via-isnad-teal-light to-accent bg-clip-text text-transparent">
                {' '}verifiable trust
              </span>
            </h1>
            <p className="text-zinc-400 text-base md:text-lg leading-8 max-w-2xl mx-auto">
              Start with a public trust surface, then scale into higher-volume verification, richer evidence, and platform support as your agent footprint grows.
            </p>
          </div>

          <Card className="mb-8 border-isnad-teal/10 bg-white/[0.035]">
            <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.28em] text-zinc-500">
                  What every plan includes
                </div>
                <h2 className="mt-3 text-2xl font-semibold text-white">
                  The same trust foundation, different operational depth
                </h2>
                <p className="mt-3 text-sm leading-7 text-zinc-500 max-w-2xl">
                  isnad is in a hardened-but-still-iterating phase. The paid plans are aimed at teams that want help integrating it earlier and at higher volume.
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {included.map((item) => (
                  <div key={item} className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4 text-sm text-zinc-300">
                    <div className="flex items-start gap-2">
                      <CheckIcon />
                      <span>{item}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            {tiers.map((tier) => (
              <div
                key={tier.name}
                className={`relative ${tier.highlighted ? 'md:-mt-4 md:mb-[-16px]' : ''}`}
              >
                {tier.highlighted && (
                  <div className="absolute -top-3 left-1/2 z-10 -translate-x-1/2">
                    <span className="inline-flex items-center rounded-full border border-isnad-teal/30 bg-isnad-teal/15 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-isnad-teal">
                      Most active pilot tier
                    </span>
                  </div>
                )}
                <Card
                  className={`flex h-full flex-col ${
                    tier.highlighted
                      ? 'border-isnad-teal/30 bg-white/[0.05] shadow-[0_0_80px_-22px_rgba(0,212,170,0.18)]'
                      : ''
                  }`}
                >
                  <div className="mb-6">
                    <div className="flex items-center justify-between gap-4">
                      <h3 className="text-xl font-semibold text-zinc-100">{tier.name}</h3>
                      <span className="rounded-full border border-white/[0.07] bg-white/[0.03] px-3 py-1 text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
                        {tier.checks} checks
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-7 text-zinc-500">{tier.description}</p>
                  </div>

                  <div className="mb-6">
                    <span className="text-4xl font-bold text-white">{tier.price}</span>
                    <span className="ml-1 text-zinc-500 text-sm">{tier.period}</span>
                  </div>

                  <div className="mb-4 text-[10px] font-mono uppercase tracking-[0.24em] text-zinc-500">
                    Included
                  </div>

                  <ul className="mb-8 flex-1 space-y-3">
                    {tier.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-sm text-zinc-300">
                        <CheckIcon />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>

                  <TierAction href={tier.href} cta={tier.cta} highlighted={tier.highlighted} />
                </Card>
              </div>
            ))}
          </div>

          <div className="mt-16 grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
            <Card className="space-y-4">
              <div className="text-[10px] font-mono uppercase tracking-[0.28em] text-zinc-500">
                Need clarity first?
              </div>
              <h2 className="text-2xl font-semibold text-white">Start with the docs and a live profile</h2>
              <p className="text-sm leading-7 text-zinc-500">
                If you are still evaluating fit, begin with a free registration, inspect the public surface, and review the API contract before committing to a higher tier.
              </p>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Link href="/register">
                  <Button size="lg">Register an Agent</Button>
                </Link>
                <Link href="/docs">
                  <Button variant="secondary" size="lg">Read the Docs</Button>
                </Link>
              </div>
            </Card>

            <div className="grid gap-4 md:grid-cols-2">
              {faqs.map((faq) => (
                <Card key={faq.question} glow={false} className="h-full">
                  <h3 className="text-base font-semibold text-white">{faq.question}</h3>
                  <p className="mt-3 text-sm leading-7 text-zinc-500">{faq.answer}</p>
                </Card>
              ))}
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/[0.04] px-4 py-12 sm:px-6">
        <div className="max-w-6xl mx-auto flex flex-col gap-3 text-center">
          <p className="text-sm text-zinc-500">
            Questions about rollout, limits, or enterprise support?{' '}
            <a href="mailto:daniel@isnad.site" className="text-isnad-teal/80 transition-colors hover:text-isnad-teal">
              daniel@isnad.site
            </a>
          </p>
          <p className="text-xs text-zinc-700 font-mono">
            © 2026 isnad. Built with cryptography, not trust.
          </p>
        </div>
      </footer>
    </main>
  );
}
