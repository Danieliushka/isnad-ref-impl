'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import TrustChainHero from '@/components/trust-chain-hero';

const pillars = [
  {
    title: 'Cryptographic identity',
    copy: 'Bind an agent to an auditable keypair instead of a marketing claim.',
  },
  {
    title: 'Attestation evidence',
    copy: 'Track who vouched for the agent and how trust propagates through the graph.',
  },
  {
    title: 'Platform signals',
    copy: 'Bring public traces, payment behavior, and trust surfaces into one profile.',
  },
];

const proofNotes = [
  'Ed25519-backed identity',
  'Public badge and embed surface',
  'Cross-platform trust summary',
];

export default function HeroSection() {
  return (
    <section className="relative overflow-hidden px-6 pt-28 pb-14 sm:pt-32 sm:pb-20">
      <div className="absolute inset-0 hero-mesh" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(0,212,170,0.12),transparent_35%),radial-gradient(circle_at_85%_20%,rgba(99,102,241,0.14),transparent_28%),linear-gradient(180deg,rgba(5,5,7,0.85),rgba(5,5,7,1))]" />
      <div className="absolute inset-0 dot-grid opacity-10" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-black/30 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[#050507] to-transparent" />

      <div className="relative z-10 mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="max-w-2xl">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55 }}
            className="mb-6"
          >
            <span className="inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.03] px-4 py-1.5 text-[11px] font-mono tracking-[0.28em] text-zinc-400">
              <span className="h-1.5 w-1.5 rounded-full bg-isnad-teal shadow-[0_0_14px_rgba(0,212,170,0.8)]" />
              VERIFIABLE TRUST SURFACE
            </span>
          </motion.div>

          <motion.h1
            className="font-heading text-5xl font-bold tracking-tight text-white sm:text-6xl lg:text-7xl lg:leading-[0.92]"
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.75, delay: 0.1 }}
          >
            Proof,
            <span className="bg-gradient-to-r from-isnad-teal via-isnad-teal-light to-accent bg-clip-text text-transparent">
              {' '}not claims,
            </span>
            <br />
            for AI agents.
          </motion.h1>

          <motion.p
            className="mt-6 max-w-xl text-base leading-7 text-zinc-400 sm:text-lg"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.75, delay: 0.22 }}
          >
            isnad turns scattered trust signals into a public verification layer for AI agents:
            identity, attestations, platform presence, and embeddable trust proof in one place.
          </motion.p>

          <motion.div
            className="mt-8 flex flex-col gap-3 sm:flex-row"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.75, delay: 0.34 }}
          >
            <Link href="/check">
              <Button size="lg">Check an Agent</Button>
            </Link>
            <Link href="/register">
              <Button variant="secondary" size="lg">Register Your Agent</Button>
            </Link>
            <Link href="/docs">
              <Button variant="ghost" size="lg">Read API Docs</Button>
            </Link>
          </motion.div>

          <motion.div
            className="mt-8 flex flex-wrap gap-2"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.75, delay: 0.46 }}
          >
            {proofNotes.map((item) => (
              <span
                key={item}
                className="inline-flex items-center gap-2 rounded-full border border-white/[0.07] bg-white/[0.025] px-3 py-1.5 text-xs text-zinc-300"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-isnad-teal" />
                {item}
              </span>
            ))}
          </motion.div>

          <motion.div
            className="mt-10 grid gap-3 sm:grid-cols-3"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.75, delay: 0.56 }}
          >
            {pillars.map((pillar) => (
              <div
                key={pillar.title}
                className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-4 backdrop-blur-xl"
              >
                <div className="mb-3 text-[10px] font-mono uppercase tracking-[0.28em] text-isnad-teal/70">
                  trust layer
                </div>
                <h3 className="text-sm font-semibold text-white">{pillar.title}</h3>
                <p className="mt-2 text-sm leading-6 text-zinc-500">{pillar.copy}</p>
              </div>
            ))}
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="relative"
        >
          <div className="absolute inset-0 rounded-[32px] bg-[radial-gradient(circle_at_top,rgba(0,212,170,0.18),transparent_42%)] blur-3xl" />
          <div className="relative overflow-hidden rounded-[32px] border border-white/[0.08] bg-white/[0.03] p-5 shadow-[0_24px_120px_-48px_rgba(0,212,170,0.35)] backdrop-blur-2xl sm:p-6">
            <div className="flex items-center justify-between gap-4 border-b border-white/[0.08] pb-4">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500">
                  Live trust graph
                </div>
                <h2 className="mt-2 text-xl font-semibold text-white">
                  One profile, multiple proof surfaces
                </h2>
              </div>
              <div className="rounded-full border border-isnad-teal/20 bg-isnad-teal/10 px-3 py-1 text-xs font-mono text-isnad-teal">
                protocol-native
              </div>
            </div>

            <div className="mt-5 rounded-[28px] border border-white/[0.06] bg-[#07090d]/90 p-3 sm:p-4">
              <div className="mb-3 flex items-center justify-between text-[11px] font-mono uppercase tracking-[0.24em] text-zinc-500">
                <span>attestation chain</span>
                <span>visible trust context</span>
              </div>
              <div className="h-[300px] sm:h-[340px]">
                <TrustChainHero />
              </div>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {[
                { label: 'Identity', value: 'Signed' },
                { label: 'Score surface', value: 'Public' },
                { label: 'Embeds', value: 'Portable' },
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4"
                >
                  <div className="text-[10px] font-mono uppercase tracking-[0.24em] text-zinc-500">
                    {item.label}
                  </div>
                  <div className="mt-2 text-lg font-semibold text-white">{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
