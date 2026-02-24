"use client";

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Navbar } from "@/components/ui/navbar";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { listIdentities, getTrustScoreV2, type TrustScoreV2Response } from "@/lib/api";

type AgentStatus = "certified" | "pending" | "failed";
type SortKey = "score-desc" | "score-asc" | "name-az";

interface ExplorerAgent {
  agent_id: string;
  public_key: string;
  trust_score: number | null;
  total_confidence: number | null;
  platforms_checked: string[];
  status: AgentStatus;
}

const ITEMS_PER_PAGE = 10;

const sorts: { key: SortKey; label: string }[] = [
  { key: "score-desc", label: "Score (high→low)" },
  { key: "score-asc", label: "Score (low→high)" },
  { key: "name-az", label: "Name A-Z" },
];

function deriveStatus(score: number | null): AgentStatus {
  if (score === null) return "pending";
  if (score >= 0.7) return "certified";
  if (score >= 0.4) return "pending";
  return "failed";
}

function statusBadge(s: AgentStatus) {
  if (s === "certified") return { text: "Certified", variant: "success" as const };
  if (s === "pending") return { text: "Pending", variant: "warning" as const };
  return { text: "Failed", variant: "danger" as const };
}

function displayScore(score: number | null): string {
  if (score === null) return "N/A";
  return String(Math.round(score * 100));
}

export default function ExplorerPage() {
  const [agents, setAgents] = useState<ExplorerAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("score-desc");
  const [page, setPage] = useState(1);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        setLoading(true);
        setError(null);
        const { identities } = await listIdentities();

        const results: ExplorerAgent[] = await Promise.all(
          identities.map(async (id) => {
            let v2: TrustScoreV2Response | null = null;
            try {
              v2 = await getTrustScoreV2(id.agent_id);
            } catch {
              // score fetch failed — show N/A
            }
            const trust_score = v2?.trust_score ?? null;
            return {
              agent_id: id.agent_id,
              public_key: id.public_key,
              trust_score,
              total_confidence: v2?.total_confidence ?? null,
              platforms_checked: v2?.platforms_checked ?? [],
              status: deriveStatus(trust_score),
            };
          })
        );

        if (!cancelled) setAgents(results);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load agents");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    let list = agents;

    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (a) =>
          a.agent_id.toLowerCase().includes(q) ||
          a.platforms_checked.some((p) => p.toLowerCase().includes(q))
      );
    }

    list = [...list].sort((a, b) => {
      switch (sort) {
        case "score-desc": return (b.trust_score ?? -1) - (a.trust_score ?? -1);
        case "score-asc": return (a.trust_score ?? -1) - (b.trust_score ?? -1);
        case "name-az": return a.agent_id.localeCompare(b.agent_id);
      }
    });

    return list;
  }, [agents, search, sort]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage = Math.min(page, totalPages);
  const paginated = filtered.slice((safePage - 1) * ITEMS_PER_PAGE, safePage * ITEMS_PER_PAGE);
  const showStart = filtered.length === 0 ? 0 : (safePage - 1) * ITEMS_PER_PAGE + 1;
  const showEnd = Math.min(safePage * ITEMS_PER_PAGE, filtered.length);

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-6 max-w-5xl mx-auto pb-20">
        {/* Header */}
        <motion.div
          className="mb-8"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <h1 className="font-heading text-3xl md:text-4xl font-bold tracking-tight">Trust Explorer</h1>
          <p className="text-zinc-500 mt-2 text-sm">Browse and verify all registered agent identities</p>
        </motion.div>

        {/* Search */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <Input
            className="mb-6"
            placeholder="Search agents by ID or platform..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </motion.div>

        {/* Sort */}
        <motion.div
          className="flex items-center justify-end gap-4 mb-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
        >
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-2 text-sm text-zinc-300 font-mono focus:outline-none focus:ring-1 focus:ring-isnad-teal/30"
          >
            {sorts.map((s) => (
              <option key={s.key} value={s.key} className="bg-zinc-900">
                {s.label}
              </option>
            ))}
          </select>
        </motion.div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-isnad-teal border-t-transparent" />
            <span className="ml-3 text-zinc-500 text-sm">Loading agents…</span>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="text-center py-20">
            <p className="text-red-400 text-sm mb-4">Error: {error}</p>
            <Button variant="ghost" size="sm" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </div>
        )}

        {/* Content */}
        {!loading && !error && (
          <>
            {/* Desktop Table */}
            <div className="hidden md:block">
              <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/[0.06]">
                      <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">Agent</th>
                      <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">Platforms</th>
                      <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">Score</th>
                      <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">Confidence</th>
                      <th className="text-left px-6 py-4 text-[10px] font-mono text-zinc-500 tracking-[0.15em] uppercase">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <AnimatePresence mode="popLayout">
                      {paginated.map((a, i) => {
                        const sb = statusBadge(a.status);
                        return (
                          <motion.tr
                            key={a.agent_id}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            transition={{ delay: i * 0.04 }}
                            className="border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors"
                          >
                            <td className="px-6 py-4">
                              <Link href={`/check/${a.agent_id}`} className="group">
                                <span className="font-mono text-isnad-teal group-hover:text-isnad-teal-light transition-colors text-sm">
                                  {a.agent_id}
                                </span>
                              </Link>
                            </td>
                            <td className="px-6 py-4 text-zinc-400 text-xs font-mono">
                              {a.platforms_checked.length > 0 ? a.platforms_checked.join(", ") : "—"}
                            </td>
                            <td className="px-6 py-4">
                              {a.trust_score !== null ? (
                                <Badge score={Math.round(a.trust_score * 100)}>{displayScore(a.trust_score)}</Badge>
                              ) : (
                                <span className="text-zinc-600 text-xs">N/A</span>
                              )}
                            </td>
                            <td className="px-6 py-4 font-mono text-zinc-400 text-sm tabular-nums">
                              {a.total_confidence !== null ? a.total_confidence.toFixed(2) : "N/A"}
                            </td>
                            <td className="px-6 py-4">
                              <Badge variant={sb.variant}>{sb.text}</Badge>
                            </td>
                          </motion.tr>
                        );
                      })}
                    </AnimatePresence>
                  </tbody>
                </table>
                {filtered.length === 0 && (
                  <div className="px-6 py-16 text-center text-zinc-500">
                    No agents found matching your search
                  </div>
                )}
              </div>
            </div>

            {/* Mobile Cards */}
            <div className="md:hidden grid gap-3">
              <AnimatePresence mode="popLayout">
                {paginated.map((a, i) => {
                  const sb = statusBadge(a.status);
                  return (
                    <motion.div
                      key={a.agent_id}
                      initial={{ opacity: 0, y: 16 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ delay: i * 0.06 }}
                    >
                      <Link href={`/check/${a.agent_id}`}>
                        <Card className="active:scale-[0.98] transition-transform">
                          <div className="flex items-center justify-between mb-3">
                            <span className="font-mono text-isnad-teal text-sm truncate mr-2">{a.agent_id}</span>
                            {a.trust_score !== null ? (
                              <Badge score={Math.round(a.trust_score * 100)}>{displayScore(a.trust_score)}</Badge>
                            ) : (
                              <span className="text-zinc-600 text-xs">N/A</span>
                            )}
                          </div>
                          <div className="flex items-center justify-between text-sm">
                            <Badge variant={sb.variant} className="text-xs">{sb.text}</Badge>
                            <span className="text-zinc-600 text-xs font-mono">
                              {a.platforms_checked.length > 0 ? a.platforms_checked.join(", ") : "—"}
                            </span>
                          </div>
                        </Card>
                      </Link>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
              {filtered.length === 0 && (
                <div className="py-16 text-center text-zinc-500">
                  No agents found matching your search
                </div>
              )}
            </div>

            {/* Pagination */}
            {filtered.length > 0 && (
              <motion.div
                className="mt-8 flex items-center justify-between"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
              >
                <p className="text-xs text-zinc-600 font-mono">
                  {showStart}–{showEnd} of {filtered.length}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={safePage <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    ← Previous
                  </Button>
                  {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={`w-8 h-8 rounded-lg text-sm font-mono transition-all ${
                        p === safePage
                          ? 'bg-isnad-teal/10 text-isnad-teal border border-isnad-teal/30'
                          : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.04]'
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={safePage >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next →
                  </Button>
                </div>
              </motion.div>
            )}
          </>
        )}
      </main>
    </>
  );
}
