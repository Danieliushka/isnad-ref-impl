'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import TrustChainHero from '@/components/trust-chain-hero';

export default function HeroSection() {
  return (
    <section className="relative min-h-screen flex items-center justify-center px-6 overflow-hidden">
      {/* Gradient mesh background */}
      <div className="absolute inset-0 hero-mesh" />

      {/* Dot grid pattern */}
      <div className="absolute inset-0 dot-grid opacity-40" />

      {/* Trust chain visualization */}
      <div className="absolute inset-0 opacity-[0.12] pointer-events-none">
        <TrustChainHero />
      </div>

      {/* Bottom fade */}
      <div className="absolute bottom-0 left-0 right-0 h-40 bg-gradient-to-t from-[#050507] to-transparent" />

      <div className="relative z-10 text-center max-w-4xl mx-auto pt-20">
        {/* Protocol badge */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mb-8"
        >
          <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-[11px] font-mono tracking-wider text-zinc-400 border border-white/[0.08] bg-white/[0.02]">
            <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal animate-pulse" />
            TRUST PROTOCOL v1.0
          </span>
        </motion.div>

        {/* Heading */}
        <motion.h1
          className="font-heading text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-bold tracking-tight leading-[0.95] mb-8"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.15 }}
        >
          <span className="bg-gradient-to-r from-isnad-teal via-isnad-teal-light to-accent bg-clip-text text-transparent">
            Trust Infrastructure
          </span>
          <br />
          <span className="text-white">for AI Agents</span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          className="text-base md:text-lg text-zinc-500 mb-12 max-w-xl mx-auto leading-relaxed"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3 }}
        >
          Cryptographic verification, behavioral analysis, and attestation
          chains&nbsp;&mdash; so agents can prove they are who they claim to be.
        </motion.p>

        {/* CTAs */}
        <motion.div
          className="flex flex-col sm:flex-row gap-4 justify-center"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.45 }}
        >
          <Link href="/check">
            <Button size="lg">Check an Agent →</Button>
          </Link>
          <Link href="/register">
            <Button variant="secondary" size="lg">
              Register Your Agent
            </Button>
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
