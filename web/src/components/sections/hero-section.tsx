'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import TrustChainHero from '@/components/trust-chain-hero';

export default function HeroSection() {
  return (
    <section className="relative min-h-screen flex items-center justify-center pt-16 px-6 overflow-hidden">
      {/* Background animation */}
      <div className="absolute inset-0 opacity-20 pointer-events-none">
        <TrustChainHero />
      </div>

      <div className="relative z-10 text-center max-w-3xl mx-auto">
        <motion.h1
          className="text-5xl md:text-7xl font-bold mb-6 bg-gradient-to-r from-isnad-teal via-isnad-teal-light to-accent bg-clip-text text-transparent"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          Trust Infrastructure for AI Agents
        </motion.h1>

        <motion.p
          className="text-lg md:text-xl text-zinc-400 mb-10 max-w-xl mx-auto"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          Cryptographic verification, behavioral analysis, and attestation chains — so agents can prove they are who they claim to be.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4 }}
        >
          <Link href="/check">
            <Button size="lg">Check an Agent →</Button>
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
