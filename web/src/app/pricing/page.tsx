import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Pricing — isnad',
  description: 'Simple, transparent pricing for AI agent trust verification. Free tier included.',
};

const tiers = [
  {
    name: 'Free',
    price: '$0',
    period: '/month',
    description: 'For individual developers and small projects getting started with agent trust.',
    checks: '100',
    features: [
      '100 trust checks/month',
      'Basic trust scoring (0–100)',
      'Public agent profiles',
      'Community support',
      'REST API access',
    ],
    cta: 'Get Started Free',
    href: '/register',
    highlighted: false,
  },
  {
    name: 'Pro',
    price: '$29',
    period: '/month',
    description: 'For teams and platforms integrating trust verification at scale.',
    checks: '10,000',
    features: [
      '10,000 trust checks/month',
      'Full category breakdown',
      'Attestation chain analysis',
      'Takeover detection alerts',
      'Priority API rate limits',
      'Webhook notifications',
      'Email support',
    ],
    cta: 'Start Pro Trial',
    href: 'mailto:daniel@isnad.site?subject=isnad%20Pro',
    highlighted: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    description: 'For platforms requiring unlimited checks, SLAs, and dedicated infrastructure.',
    checks: 'Unlimited',
    features: [
      'Unlimited trust checks',
      'Dedicated infrastructure',
      'Custom scoring modules',
      'On-premise deployment option',
      'SSO & team management',
      'SLA guarantee (99.9%)',
      'Dedicated support engineer',
      'Custom integrations',
    ],
    cta: 'Contact Us',
    href: 'mailto:daniel@isnad.site?subject=isnad%20Enterprise',
    highlighted: false,
  },
];

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0 mt-0.5">
      <path d="M4 8l3 3 5-5" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function PricingPage() {
  return (
    <main className="min-h-screen">
      <Navbar />

      <section className="pt-32 pb-24 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto">
          {/* Header */}
          <div className="text-center mb-16">
            <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-isnad-teal/60 mb-3 block">
              Pricing
            </span>
            <h1 className="font-heading text-4xl md:text-5xl font-bold tracking-tight mb-4">
              Simple, Transparent{' '}
              <span className="bg-gradient-to-r from-isnad-teal via-isnad-teal-light to-accent bg-clip-text text-transparent">
                Pricing
              </span>
            </h1>
            <p className="text-zinc-500 text-sm max-w-lg mx-auto leading-relaxed">
              Start free. Scale as your agent network grows. No hidden fees, no credit card required for the free tier.
            </p>
          </div>

          {/* Tiers Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {tiers.map((tier) => (
              <div
                key={tier.name}
                className={`relative ${tier.highlighted ? 'md:-mt-4 md:mb-[-16px]' : ''}`}
              >
                {tier.highlighted && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-10">
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-isnad-teal/20 text-isnad-teal border border-isnad-teal/30">
                      Most Popular
                    </span>
                  </div>
                )}
                <Card
                  className={`h-full flex flex-col ${
                    tier.highlighted
                      ? 'border-isnad-teal/30 bg-white/[0.04] shadow-[0_0_60px_-15px_rgba(0,212,170,0.15)]'
                      : ''
                  }`}
                >
                  <div className="mb-6">
                    <h3 className="text-lg font-semibold text-zinc-200 mb-1">{tier.name}</h3>
                    <p className="text-zinc-600 text-xs leading-relaxed">{tier.description}</p>
                  </div>

                  <div className="mb-6">
                    <span className="text-3xl font-bold text-white">{tier.price}</span>
                    <span className="text-zinc-500 text-sm">{tier.period}</span>
                  </div>

                  <div className="mb-2 text-[10px] font-mono tracking-[0.15em] uppercase text-zinc-500">
                    {tier.checks} checks/month
                  </div>

                  <div className="border-t border-white/[0.06] my-4" />

                  <ul className="space-y-3 mb-8 flex-1">
                    {tier.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-sm text-zinc-400">
                        <CheckIcon />
                        {feature}
                      </li>
                    ))}
                  </ul>

                  <Link href={tier.href}>
                    <Button
                      variant={tier.highlighted ? 'primary' : 'secondary'}
                      size="md"
                      className="w-full"
                    >
                      {tier.cta}
                    </Button>
                  </Link>
                </Card>
              </div>
            ))}
          </div>

          {/* FAQ / Bottom note */}
          <div className="mt-16 text-center">
            <p className="text-zinc-600 text-xs">
              All plans include REST API access, Python SDK, and CLI tools.{' '}
              <a href="mailto:daniel@isnad.site" className="text-isnad-teal/70 hover:text-isnad-teal transition-colors">
                Questions? Contact us.
              </a>
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.04] py-12 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-xs text-zinc-700 font-mono">
            © 2025 isnad. Built with cryptography, not trust.
          </p>
        </div>
      </footer>
    </main>
  );
}
