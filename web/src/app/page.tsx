"use client";

import { Navbar } from "@/components/ui/navbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import TrustChainHero from "@/components/trust-chain-hero";
import { motion } from "framer-motion";
import Link from "next/link";

const stats = [
  { value: "1,029", label: "Tests Passing" },
  { value: "6", label: "Trust Categories" },
  { value: "<200ms", label: "Check Time" },
  { value: "100%", label: "Open Source" },
];

const features = [
  {
    icon: "🔍",
    title: "Trust Check",
    desc: "Enter any agent ID — get a detailed trust report with scores across 6 categories, risk flags, and attestation chain.",
  },
  {
    icon: "📜",
    title: "Certifications",
    desc: "Agents that pass verification receive cryptographic certificates with TTL-based decay and automatic re-evaluation.",
  },
  {
    icon: "🔗",
    title: "Attestation Chains",
    desc: "Every trust claim is backed by an isnad — a cryptographic chain of attestations traceable to its origin.",
  },
  {
    icon: "🤖",
    title: "ACP Integration",
    desc: "Plug into Agent Commerce Protocol for automated quality verification of agent-to-agent transactions.",
  },
];

export default function Home() {
  return (
    <>
      <Navbar />

      {/* Hero */}
      <main className="min-h-screen">
        <section className="flex flex-col items-center justify-center px-6 pt-32 pb-16">
          <motion.h1
            className="text-5xl md:text-7xl font-bold text-center max-w-4xl leading-tight"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <span className="text-isnad-teal">Trust</span> Infrastructure
            <br />
            for AI Agents
          </motion.h1>
          <motion.p
            className="mt-6 text-lg text-zinc-400 text-center max-w-2xl"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            Verify, certify, and build trust with cryptographic attestations and
            behavioral analysis. Like VirusTotal, but for AI agents.
          </motion.p>
          <motion.div
            className="mt-10 flex gap-4"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
          >
            <Link href="/check">
              <Button size="lg">Check an Agent</Button>
            </Link>
            <Link href="/explorer">
              <Button variant="secondary" size="lg">
                Explorer
              </Button>
            </Link>
          </motion.div>
        </section>

        {/* Trust Chain Visualization */}
        <section className="py-16 px-6">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 }}
          >
            <TrustChainHero />
          </motion.div>
        </section>

        {/* Stats */}
        <section className="py-16 px-6 border-t border-zinc-800">
          <div className="max-w-4xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map((stat, i) => (
              <motion.div
                key={stat.label}
                className="text-center"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.8 + i * 0.1 }}
              >
                <div className="text-3xl font-bold font-mono text-isnad-teal">
                  {stat.value}
                </div>
                <div className="text-sm text-zinc-500 mt-1">{stat.label}</div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* Features */}
        <section className="py-16 px-6">
          <div className="max-w-5xl mx-auto">
            <h2 className="text-3xl font-bold text-center mb-12">
              How it works
            </h2>
            <div className="grid md:grid-cols-2 gap-6">
              {features.map((f, i) => (
                <motion.div
                  key={f.title}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 1 + i * 0.15 }}
                >
                  <Card className="p-6 h-full">
                    <div className="text-2xl mb-3">{f.icon}</div>
                    <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
                    <p className="text-zinc-400 text-sm">{f.desc}</p>
                  </Card>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="py-20 px-6 border-t border-zinc-800">
          <div className="max-w-2xl mx-auto text-center">
            <h2 className="text-2xl font-bold mb-4">
              Ready to verify trust?
            </h2>
            <p className="text-zinc-400 mb-8">
              isnad is open source and free to use. Check any agent now.
            </p>
            <Link href="/check">
              <Button size="lg">Get Started</Button>
            </Link>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-zinc-800 py-8 px-6">
          <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-isnad-teal font-bold">isnad</span>
              <span className="text-zinc-500 text-sm">
                Trust Infrastructure for AI Agents
              </span>
            </div>
            <div className="flex gap-6 text-sm text-zinc-500">
              <a
                href="https://github.com/gendolf/isnad-ref-impl"
                className="hover:text-zinc-300 transition"
              >
                GitHub
              </a>
              <Link href="/docs" className="hover:text-zinc-300 transition">
                Docs
              </Link>
              <a
                href="https://t.me/agent_realm"
                className="hover:text-zinc-300 transition"
              >
                Community
              </a>
            </div>
          </div>
        </footer>
      </main>
    </>
  );
}
