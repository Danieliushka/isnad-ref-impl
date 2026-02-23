'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { createIdentity } from '@/lib/api';

const platforms = ['ugig', 'Clawk', 'AgentMail', 'custom'] as const;

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [platform, setPlatform] = useState<string>('ugig');
  const [platformHandle, setPlatformHandle] = useState('');
  const [publicKey, setPublicKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !platformHandle.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const result = await createIdentity({
        name: name.trim(),
        platform,
        platform_handle: platformHandle.trim(),
        public_key: publicKey.trim() || undefined,
      });
      router.push(`/check/${encodeURIComponent(result.agent_id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Navbar />
      <main className="min-h-screen flex flex-col items-center justify-center px-6 pt-24 pb-20">
        <motion.div
          className="w-full max-w-xl"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          {/* Header */}
          <div className="text-center mb-10">
            <motion.div
              className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-isnad-teal/10 border border-isnad-teal/20 mb-6"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', delay: 0.2 }}
            >
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                <circle cx="16" cy="12" r="5" stroke="#00d4aa" strokeWidth="1.5" />
                <path d="M6 26c0-5.523 4.477-10 10-10s10 4.477 10 10" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" />
                <path d="M22 8l4 4M26 8l-4 4" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </motion.div>
            <h1 className="font-heading text-4xl md:text-5xl font-bold tracking-tight mb-3">
              Register Your{' '}
              <span className="bg-gradient-to-r from-isnad-teal via-isnad-teal-light to-accent bg-clip-text text-transparent">
                Agent
              </span>
            </h1>
            <p className="text-zinc-500 text-base leading-relaxed max-w-md mx-auto">
              Create a cryptographic identity for your AI agent and start building trust through verifiable attestations.
            </p>
          </div>

          {/* Form */}
          <Card>
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Agent Name */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Agent Name
                </label>
                <Input
                  placeholder="e.g. my-trading-bot"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>

              {/* Platform */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Platform
                </label>
                <select
                  value={platform}
                  onChange={(e) => setPlatform(e.target.value)}
                  className="w-full bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-3 text-[var(--foreground)] font-mono text-sm focus:outline-none focus:ring-1 focus:ring-isnad-teal/30 focus:border-isnad-teal/30 transition-all duration-300"
                >
                  {platforms.map((p) => (
                    <option key={p} value={p} className="bg-zinc-900">
                      {p}
                    </option>
                  ))}
                </select>
              </div>

              {/* Platform Handle */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Platform Handle / ID
                </label>
                <Input
                  placeholder="e.g. @mybot or agent-123"
                  value={platformHandle}
                  onChange={(e) => setPlatformHandle(e.target.value)}
                  required
                />
              </div>

              {/* Public Key (optional) */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Public Key <span className="text-zinc-600 normal-case tracking-normal">(optional — one will be generated)</span>
                </label>
                <Input
                  placeholder="Ed25519 public key hex..."
                  value={publicKey}
                  onChange={(e) => setPublicKey(e.target.value)}
                  className="text-xs"
                />
              </div>

              {/* Error */}
              {error && (
                <motion.div
                  className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                >
                  {error}
                </motion.div>
              )}

              {/* Submit */}
              <Button
                type="submit"
                size="lg"
                className="w-full"
                disabled={loading || !name.trim() || !platformHandle.trim()}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Creating Identity...
                  </span>
                ) : (
                  'Register Agent →'
                )}
              </Button>
            </form>
          </Card>

          {/* Info note */}
          <motion.p
            className="text-center text-xs text-zinc-600 mt-6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            Registration creates an Ed25519 keypair. Your agent can then receive attestations from other verified agents.
          </motion.p>
        </motion.div>
      </main>
    </>
  );
}
