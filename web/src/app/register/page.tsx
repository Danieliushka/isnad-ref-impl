'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { registerAgent, type RegisterAgentResponse, type PlatformEntry } from '@/lib/api';

const agentTypes = [
  { value: 'autonomous', label: 'Autonomous' },
  { value: 'tool-calling', label: 'Tool-Calling' },
  { value: 'human-supervised', label: 'Human-Supervised' },
] as const;

export default function RegisterPage() {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [agentType, setAgentType] = useState<string>('autonomous');
  const [platforms, setPlatforms] = useState<PlatformEntry[]>([{ name: '', url: '' }]);
  const [capInput, setCapInput] = useState('');
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [offerings, setOfferings] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RegisterAgentResponse | null>(null);

  function addPlatform() {
    setPlatforms([...platforms, { name: '', url: '' }]);
  }

  function removePlatform(idx: number) {
    setPlatforms(platforms.filter((_, i) => i !== idx));
  }

  function updatePlatform(idx: number, field: 'name' | 'url', value: string) {
    const updated = [...platforms];
    updated[idx] = { ...updated[idx], [field]: value };
    setPlatforms(updated);
  }

  function handleCapKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if ((e.key === 'Enter' || e.key === ',') && capInput.trim()) {
      e.preventDefault();
      const tag = capInput.trim().replace(/,$/, '');
      if (tag && !capabilities.includes(tag)) {
        setCapabilities([...capabilities, tag]);
      }
      setCapInput('');
    }
  }

  function removeCapability(cap: string) {
    setCapabilities(capabilities.filter((c) => c !== cap));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const resp = await registerAgent({
        name: name.trim(),
        description: description.trim(),
        agent_type: agentType as 'autonomous' | 'tool-calling' | 'human-supervised',
        platforms: platforms.filter((p) => p.name.trim()),
        capabilities,
        offerings: offerings.trim(),
        avatar_url: avatarUrl.trim() || undefined,
        contact_email: contactEmail.trim() || undefined,
      });
      setResult(resp);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setLoading(false);
    }
  }

  const selectClass =
    'w-full bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-3 text-[var(--foreground)] font-mono text-sm focus:outline-none focus:ring-1 focus:ring-isnad-teal/30 focus:border-isnad-teal/30 transition-all duration-300';

  // Success state
  if (result) {
    return (
      <>
        <Navbar />
        <main className="min-h-screen flex flex-col items-center justify-center px-6 pt-24 pb-20">
          <motion.div
            className="w-full max-w-xl"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5 }}
          >
            <div className="text-center mb-8">
              <motion.div
                className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 mb-6"
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: 'spring', delay: 0.2 }}
              >
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2">
                  <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </motion.div>
              <h1 className="font-heading text-3xl md:text-4xl font-bold tracking-tight mb-2">
                Agent Registered!
              </h1>
              <p className="text-zinc-500 text-sm">Your agent identity has been created successfully.</p>
            </div>

            <Card>
              <div className="space-y-5">
                {/* Agent ID */}
                <div>
                  <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                    Agent ID
                  </label>
                  <div className="bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-3 font-mono text-sm text-isnad-teal break-all">
                    {result.agent_id}
                  </div>
                </div>

                {/* Public Key */}
                <div>
                  <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                    Public Key (Ed25519)
                  </label>
                  <div className="bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-3 font-mono text-xs text-zinc-300 break-all">
                    {result.public_key}
                  </div>
                </div>

                {/* API Key — WARNING */}
                <div>
                  <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                    API Key
                  </label>
                  <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl px-4 py-3 font-mono text-sm text-amber-300 break-all">
                    {result.api_key}
                  </div>
                  <div className="mt-3 p-3 rounded-xl bg-red-500/10 border border-red-500/20">
                    <p className="text-red-400 text-xs font-medium flex items-center gap-2">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                        <line x1="12" y1="9" x2="12" y2="13" />
                        <line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                      Save this API key now! It will NOT be shown again.
                    </p>
                  </div>
                </div>

                {/* Created At */}
                <div>
                  <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                    Created At
                  </label>
                  <div className="text-zinc-400 text-sm font-mono">
                    {new Date(result.created_at).toLocaleString()}
                  </div>
                </div>

                {/* Copy buttons */}
                <div className="flex gap-3 pt-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigator.clipboard.writeText(result.api_key)}
                  >
                    Copy API Key
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigator.clipboard.writeText(result.agent_id)}
                  >
                    Copy Agent ID
                  </Button>
                </div>
              </div>
            </Card>
          </motion.div>
        </main>
      </>
    );
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
                  Agent Name *
                </label>
                <Input
                  placeholder="e.g. my-trading-bot"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Description
                </label>
                <textarea
                  placeholder="What does your agent do?"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  maxLength={1000}
                  className={selectClass + ' resize-none'}
                />
              </div>

              {/* Agent Type */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Agent Type
                </label>
                <select
                  value={agentType}
                  onChange={(e) => setAgentType(e.target.value)}
                  className={selectClass}
                >
                  {agentTypes.map((t) => (
                    <option key={t.value} value={t.value} className="bg-zinc-900">
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Platforms */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Platforms
                </label>
                <div className="space-y-2">
                  <AnimatePresence>
                    {platforms.map((p, idx) => (
                      <motion.div
                        key={idx}
                        className="flex gap-2 items-center"
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                      >
                        <Input
                          placeholder="Platform name"
                          value={p.name}
                          onChange={(e) => updatePlatform(idx, 'name', e.target.value)}
                          className="flex-1"
                        />
                        <Input
                          placeholder="URL (optional)"
                          value={p.url}
                          onChange={(e) => updatePlatform(idx, 'url', e.target.value)}
                          className="flex-1"
                        />
                        {platforms.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removePlatform(idx)}
                            className="text-zinc-500 hover:text-red-400 transition-colors p-2"
                          >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <line x1="18" y1="6" x2="6" y2="18" />
                              <line x1="6" y1="6" x2="18" y2="18" />
                            </svg>
                          </button>
                        )}
                      </motion.div>
                    ))}
                  </AnimatePresence>
                  <button
                    type="button"
                    onClick={addPlatform}
                    className="text-isnad-teal text-xs font-mono hover:text-isnad-teal-light transition-colors"
                  >
                    + Add platform
                  </button>
                </div>
              </div>

              {/* Capabilities (tag input) */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Capabilities
                </label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {capabilities.map((cap) => (
                    <span
                      key={cap}
                      className="inline-flex items-center gap-1 bg-isnad-teal/10 border border-isnad-teal/20 rounded-lg px-2.5 py-1 text-xs text-isnad-teal font-mono"
                    >
                      {cap}
                      <button
                        type="button"
                        onClick={() => removeCapability(cap)}
                        className="hover:text-red-400 transition-colors"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <Input
                  placeholder="Type a capability and press Enter..."
                  value={capInput}
                  onChange={(e) => setCapInput(e.target.value)}
                  onKeyDown={handleCapKeyDown}
                />
              </div>

              {/* Offerings */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Offerings
                </label>
                <textarea
                  placeholder="What does your agent offer or sell?"
                  value={offerings}
                  onChange={(e) => setOfferings(e.target.value)}
                  rows={2}
                  maxLength={2000}
                  className={selectClass + ' resize-none'}
                />
              </div>

              {/* Avatar URL */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Avatar URL <span className="text-zinc-600 normal-case tracking-normal">(optional)</span>
                </label>
                <Input
                  placeholder="https://example.com/avatar.png"
                  value={avatarUrl}
                  onChange={(e) => setAvatarUrl(e.target.value)}
                />
              </div>

              {/* Contact Email */}
              <div>
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Contact Email <span className="text-zinc-600 normal-case tracking-normal">(optional)</span>
                </label>
                <Input
                  type="email"
                  placeholder="agent@example.com"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
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
                disabled={loading || !name.trim()}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Registering...
                  </span>
                ) : (
                  'Register Agent →'
                )}
              </Button>
            </form>
          </Card>

          <motion.p
            className="text-center text-xs text-zinc-600 mt-6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            Registration generates an Ed25519 keypair and API key. Your agent can then receive attestations from other verified agents.
          </motion.p>
        </motion.div>
      </main>
    </>
  );
}
