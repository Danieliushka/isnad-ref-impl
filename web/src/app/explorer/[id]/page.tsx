'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Navbar } from '@/components/ui/navbar';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import TrustScoreRing from '@/components/trust-score-ring';
import { getAgentDetail, type AgentDetailResponse } from '@/lib/api';

const typeColors: Record<string, { bg: string; text: string; label: string }> = {
  autonomous: { bg: 'bg-purple-500/15', text: 'text-purple-400', label: 'Autonomous' },
  'tool-calling': { bg: 'bg-blue-500/15', text: 'text-blue-400', label: 'Tool-Calling' },
  'human-supervised': { bg: 'bg-amber-500/15', text: 'text-amber-400', label: 'Human-Supervised' },
};

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500 mb-2">
      {children}
    </label>
  );
}

function Field({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-3 font-mono text-sm text-zinc-300 break-all">
      {children}
    </div>
  );
}

export default function AgentDetailPage() {
  const params = useParams();
  const agentId = params.id as string;
  const [agent, setAgent] = useState<AgentDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!agentId) return;
    setLoading(true);
    getAgentDetail(agentId)
      .then(setAgent)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load agent'))
      .finally(() => setLoading(false));
  }, [agentId]);

  if (loading) {
    return (
      <>
        <Navbar />
        <main className="min-h-screen flex items-center justify-center pt-24">
          <div className="animate-pulse text-zinc-600 font-mono text-sm">Loading agent...</div>
        </main>
      </>
    );
  }

  if (error || !agent) {
    return (
      <>
        <Navbar />
        <main className="min-h-screen flex flex-col items-center justify-center pt-24 px-6">
          <div className="text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-500/10 mb-4">
              <span className="text-2xl">⚠️</span>
            </div>
            <p className="text-red-400 text-sm mb-4">{error || 'Agent not found'}</p>
            <Link href="/explorer">
              <Button variant="ghost" size="sm">← Back to Explorer</Button>
            </Link>
          </div>
        </main>
      </>
    );
  }

  const meta = agent.metadata;
  const typeInfo = typeColors[meta.agent_type || 'autonomous'] || typeColors['autonomous'];

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-4 sm:px-6 max-w-3xl mx-auto pb-20">
        {/* Back link */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mb-6"
        >
          <Link href="/explorer" className="text-xs text-zinc-600 hover:text-zinc-400 font-mono transition-colors">
            ← Back to Explorer
          </Link>
        </motion.div>

        {/* Header */}
        <motion.div
          className="flex flex-col sm:flex-row items-start gap-6 mb-8"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          {/* Avatar */}
          <div className="shrink-0">
            {meta.avatar_url ? (
              <img
                src={meta.avatar_url}
                alt={agent.name}
                className="w-20 h-20 rounded-2xl object-cover border border-white/[0.1]"
              />
            ) : (
              <div className="w-20 h-20 rounded-2xl bg-white/[0.06] border border-white/[0.1] flex items-center justify-center text-2xl font-bold text-zinc-400">
                {agent.name.charAt(0).toUpperCase()}
              </div>
            )}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <h1 className="font-heading text-3xl md:text-4xl font-bold tracking-tight text-white">
                {agent.name}
              </h1>
              {agent.is_certified && (
                <span className="text-xs font-medium text-isnad-teal bg-isnad-teal/10 px-2.5 py-1 rounded-full border border-isnad-teal/20">
                  ✓ Certified
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mb-3">
              <span className={`inline-flex items-center px-2.5 py-1 rounded-lg text-[10px] font-medium tracking-wide uppercase ${typeInfo.bg} ${typeInfo.text}`}>
                {typeInfo.label}
              </span>
              <span className="text-zinc-600 text-xs font-mono">
                {agent.attestation_count} attestation{agent.attestation_count !== 1 ? 's' : ''}
              </span>
            </div>
            {meta.description && (
              <p className="text-zinc-400 text-sm leading-relaxed">{meta.description}</p>
            )}
          </div>

          {/* Trust Score */}
          <div className="shrink-0 self-center sm:self-start">
            <TrustScoreRing score={Math.round(agent.trust_score)} size={120} strokeWidth={5} />
          </div>
        </motion.div>

        {/* Details */}
        <motion.div
          className="space-y-6"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          {/* Identity */}
          <Card>
            <div className="space-y-4">
              <h2 className="font-heading text-lg font-semibold text-white">Identity</h2>
              <div>
                <Label>Agent ID</Label>
                <Field><span className="text-isnad-teal">{agent.agent_id}</span></Field>
              </div>
              <div>
                <Label>Public Key (Ed25519)</Label>
                <Field><span className="text-xs">{agent.public_key}</span></Field>
              </div>
              {agent.last_checked && (
                <div>
                  <Label>Last Checked</Label>
                  <div className="text-zinc-400 text-sm font-mono">
                    {new Date(agent.last_checked).toLocaleString()}
                  </div>
                </div>
              )}
            </div>
          </Card>

          {/* Capabilities & Platforms */}
          {((meta.capabilities && meta.capabilities.length > 0) || (meta.platforms && meta.platforms.length > 0)) && (
            <Card>
              <div className="space-y-4">
                <h2 className="font-heading text-lg font-semibold text-white">Capabilities & Platforms</h2>
                {meta.capabilities && meta.capabilities.length > 0 && (
                  <div>
                    <Label>Capabilities</Label>
                    <div className="flex flex-wrap gap-2">
                      {meta.capabilities.map((cap) => (
                        <span
                          key={cap}
                          className="inline-flex items-center bg-isnad-teal/10 border border-isnad-teal/20 rounded-lg px-2.5 py-1 text-xs text-isnad-teal font-mono"
                        >
                          {cap}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {meta.platforms && meta.platforms.length > 0 && (
                  <div>
                    <Label>Platforms</Label>
                    <div className="space-y-2">
                      {meta.platforms.map((p, i) => (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-sm text-zinc-300 font-medium">{p.name}</span>
                          {p.url && (
                            <a
                              href={p.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-isnad-teal hover:text-isnad-teal-light transition-colors font-mono truncate"
                            >
                              {p.url}
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Offerings */}
          {meta.offerings && (
            <Card>
              <div className="space-y-3">
                <h2 className="font-heading text-lg font-semibold text-white">Offerings</h2>
                <p className="text-zinc-400 text-sm leading-relaxed">{meta.offerings}</p>
              </div>
            </Card>
          )}

          {/* Contact */}
          {meta.contact_email && (
            <Card>
              <div className="space-y-3">
                <h2 className="font-heading text-lg font-semibold text-white">Contact</h2>
                <div>
                  <Label>Email</Label>
                  <a href={`mailto:${meta.contact_email}`} className="text-isnad-teal text-sm font-mono hover:text-isnad-teal-light transition-colors">
                    {meta.contact_email}
                  </a>
                </div>
              </div>
            </Card>
          )}

          {/* Recent Attestations */}
          {agent.recent_attestations && agent.recent_attestations.length > 0 && (
            <Card>
              <div className="space-y-4">
                <h2 className="font-heading text-lg font-semibold text-white">Recent Attestations</h2>
                <div className="space-y-3">
                  {agent.recent_attestations.map((att) => (
                    <div
                      key={att.attestation_id}
                      className="flex items-center justify-between py-2 border-b border-white/[0.05] last:border-0"
                    >
                      <div className="min-w-0">
                        <div className="text-sm text-zinc-300 font-medium truncate">
                          {att.attester_name}
                        </div>
                        <div className="text-xs text-zinc-600 font-mono">{att.scope}</div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <span className={`text-sm font-mono font-bold ${att.value >= 0.7 ? 'text-isnad-teal' : att.value >= 0.4 ? 'text-amber-400' : 'text-red-400'}`}>
                          {(att.value * 100).toFixed(0)}%
                        </span>
                        <span className="text-[10px] text-zinc-600 font-mono">
                          {new Date(att.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}
        </motion.div>
      </main>
    </>
  );
}
