'use client';

import { useState, useMemo, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import { Navbar } from '@/components/ui/navbar';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import AgentCard from '@/components/agent-card';
import { listAgents, type AgentProfile } from '@/lib/api';

type SortKey = 'trust' | 'name' | 'newest';
type AgentType = '' | 'autonomous' | 'tool-calling' | 'human-supervised';
type ScoreRange = '' | 'high' | 'medium' | 'low';

const sortOptions: { key: SortKey; label: string }[] = [
  { key: 'trust', label: 'Trust Score' },
  { key: 'newest', label: 'Newest' },
  { key: 'name', label: 'Name A–Z' },
];

const typeFilters: { key: AgentType; label: string }[] = [
  { key: '', label: 'All Types' },
  { key: 'autonomous', label: 'Autonomous' },
  { key: 'tool-calling', label: 'Tool-Calling' },
  { key: 'human-supervised', label: 'Human-Supervised' },
];

const scoreFilters: { key: ScoreRange; label: string }[] = [
  { key: '', label: 'Any Score' },
  { key: 'high', label: '80+' },
  { key: 'medium', label: '50–79' },
  { key: 'low', label: '0–49' },
];

function SkeletonCard() {
  return (
    <div className="bg-white/[0.03] backdrop-blur-xl border border-white/[0.07] rounded-2xl p-5 animate-pulse">
      <div className="flex items-start gap-4">
        <div className="w-20 h-20 rounded-full bg-white/[0.06]" />
        <div className="flex-1 space-y-3">
          <div className="h-4 w-32 bg-white/[0.06] rounded" />
          <div className="h-3 w-20 bg-white/[0.04] rounded" />
          <div className="h-3 w-full bg-white/[0.04] rounded" />
        </div>
      </div>
      <div className="flex gap-2 mt-4 pt-3 border-t border-white/[0.05]">
        <div className="h-6 w-16 bg-white/[0.04] rounded-lg" />
        <div className="h-6 w-16 bg-white/[0.04] rounded-lg" />
      </div>
    </div>
  );
}

export default function ExplorerPage() {
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortKey>('trust');
  const [typeFilter, setTypeFilter] = useState<AgentType>('');
  const [scoreFilter, setScoreFilter] = useState<ScoreRange>('');
  const [page, setPage] = useState(1);
  const limit = 12;

  const fetchAgents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await listAgents({
        page,
        limit,
        agent_type: typeFilter || undefined,
        search: search || undefined,
      });
      setAgents(res.agents);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load agents');
    } finally {
      setLoading(false);
    }
  }, [page, typeFilter, search]);

  useEffect(() => {
    const timeout = setTimeout(fetchAgents, search ? 300 : 0);
    return () => clearTimeout(timeout);
  }, [fetchAgents, search]);

  const filtered = useMemo(() => {
    let list = [...agents];

    // Score filter (client-side since API may not support it)
    if (scoreFilter === 'high') list = list.filter(a => a.trust_score >= 80);
    else if (scoreFilter === 'medium') list = list.filter(a => a.trust_score >= 50 && a.trust_score < 80);
    else if (scoreFilter === 'low') list = list.filter(a => a.trust_score < 50);

    // Sort
    list.sort((a, b) => {
      switch (sort) {
        case 'trust': return b.trust_score - a.trust_score;
        case 'name': return a.name.localeCompare(b.name);
        case 'newest': return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
    });

    return list;
  }, [agents, scoreFilter, sort]);

  function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
    return (
      <button
        onClick={onClick}
        className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 border ${
          active
            ? 'bg-isnad-teal/15 text-isnad-teal border-isnad-teal/30'
            : 'bg-white/[0.03] text-zinc-500 border-white/[0.06] hover:text-zinc-300 hover:border-white/[0.12]'
        }`}
      >
        {children}
      </button>
    );
  }

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-4 sm:px-6 max-w-6xl mx-auto pb-20">
        {/* Header */}
        <motion.div
          className="mb-10"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <h1 className="font-heading text-4xl md:text-5xl font-bold tracking-tight">
            Agent Explorer
          </h1>
          <p className="text-zinc-500 mt-3 text-sm md:text-base max-w-lg">
            Discover trusted AI agents. Verify their identity, reputation, and capabilities.
          </p>
        </motion.div>

        {/* Search + Filters */}
        <motion.div
          className="space-y-4 mb-8"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          {/* Search bar */}
          <div className="relative">
            <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <Input
              className="pl-11"
              placeholder="Search by name, platform, or capability..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            />
          </div>

          {/* Filter pills */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-mono mr-1">Type</span>
            {typeFilters.map(f => (
              <Pill key={f.key} active={typeFilter === f.key} onClick={() => { setTypeFilter(f.key); setPage(1); }}>
                {f.label}
              </Pill>
            ))}
            <div className="w-px h-5 bg-white/[0.08] mx-2" />
            <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-mono mr-1">Score</span>
            {scoreFilters.map(f => (
              <Pill key={f.key} active={scoreFilter === f.key} onClick={() => setScoreFilter(f.key)}>
                {f.label}
              </Pill>
            ))}
          </div>

          {/* Sort */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-mono">Sort</span>
            {sortOptions.map(s => (
              <Pill key={s.key} active={sort === s.key} onClick={() => setSort(s.key)}>
                {s.label}
              </Pill>
            ))}
          </div>
        </motion.div>

        {/* Loading skeletons */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="text-center py-20">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-500/10 mb-4">
              <span className="text-2xl">⚠️</span>
            </div>
            <p className="text-red-400 text-sm mb-4">{error}</p>
            <Button variant="ghost" size="sm" onClick={fetchAgents}>
              Try Again
            </Button>
          </div>
        )}

        {/* Agent Grid */}
        {!loading && !error && (
          <>
            {filtered.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filtered.map((agent, i) => (
                  <AgentCard key={agent.agent_id} agent={agent} index={i} />
                ))}
              </div>
            ) : (
              /* Empty state */
              <motion.div
                className="text-center py-24"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
              >
                <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-white/[0.04] border border-white/[0.06] mb-6">
                  <span className="text-3xl">🔍</span>
                </div>
                <h3 className="text-lg font-semibold text-zinc-300 mb-2">
                  No agents found
                </h3>
                <p className="text-zinc-600 text-sm mb-6 max-w-sm mx-auto">
                  {search || typeFilter || scoreFilter
                    ? 'Try adjusting your filters or search terms.'
                    : 'No agents registered yet. Be the first to join the trust network.'}
                </p>
                <Link href="/register">
                  <Button>Register Your Agent</Button>
                </Link>
              </motion.div>
            )}

            {/* Pagination */}
            {filtered.length > 0 && (
              <motion.div
                className="mt-10 flex items-center justify-center gap-3"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
              >
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(p => p - 1)}
                >
                  ← Previous
                </Button>
                <span className="text-xs text-zinc-600 font-mono tabular-nums px-3">
                  Page {page}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={agents.length < limit}
                  onClick={() => setPage(p => p + 1)}
                >
                  Next →
                </Button>
              </motion.div>
            )}
          </>
        )}
      </main>
    </>
  );
}
