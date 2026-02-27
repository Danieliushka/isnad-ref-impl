'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import AnimatedSection from './animated-section';
import type { AgentProfile } from '@/lib/api';

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export default function TrustExplorerLive() {
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('/api/v1/agents?limit=8');
        if (!res.ok) return;
        const data = await res.json();
        setAgents(data.agents || []);
      } catch {
        // keep empty
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
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
            Real registered agents and their trust scores
          </p>
        </div>
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">Agent</th>
                  <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">Score</th>
                  <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">Type</th>
                  <th className="text-right px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">Registered</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={4} className="px-6 py-8 text-center text-zinc-600 text-sm">Loading agents…</td>
                  </tr>
                ) : agents.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-6 py-8 text-center text-zinc-600 text-sm">No agents registered yet</td>
                  </tr>
                ) : (
                  agents.map((a) => {
                    const score = Math.round(a.trust_score);
                    return (
                      <tr
                        key={a.agent_id}
                        className="border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors cursor-pointer"
                      >
                        <td className="px-6 py-4">
                          <Link href={`/agents/${a.agent_id}`} className="font-mono text-sm text-isnad-teal hover:text-isnad-teal-light transition-colors">
                            {a.name}
                          </Link>
                        </td>
                        <td className="px-6 py-4">
                          {score === 0 ? (
                            <span className="text-xs text-zinc-600 italic">Unscored</span>
                          ) : (
                            <Badge score={score}>{score}</Badge>
                          )}
                        </td>
                        <td className="px-6 py-4 text-zinc-400 text-xs capitalize">{a.agent_type}</td>
                        <td className="px-6 py-4 text-right text-zinc-600 text-xs font-mono">
                          {timeAgo(a.created_at)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <div className="px-6 py-4 border-t border-white/[0.04] text-center">
            <Link href="/explorer" className="text-isnad-teal/70 hover:text-isnad-teal text-sm font-medium transition-colors">
              View all agents →
            </Link>
          </div>
        </div>
      </div>
    </AnimatedSection>
  );
}
