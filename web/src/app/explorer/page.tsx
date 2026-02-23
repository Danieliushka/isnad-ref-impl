"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Navbar } from "@/components/ui/navbar";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { mockAgents, type AgentStatus, type ExplorerAgent } from "@/lib/mock-data";

type FilterStatus = "all" | AgentStatus;
type SortKey = "score-desc" | "score-asc" | "recent" | "name-az";

const ITEMS_PER_PAGE = 10;

const filters: { key: FilterStatus; label: string }[] = [
  { key: "all", label: "All" },
  { key: "certified", label: "Certified" },
  { key: "pending", label: "Pending" },
  { key: "failed", label: "Failed" },
];

const sorts: { key: SortKey; label: string }[] = [
  { key: "score-desc", label: "Score (high→low)" },
  { key: "score-asc", label: "Score (low→high)" },
  { key: "recent", label: "Recently checked" },
  { key: "name-az", label: "Name A-Z" },
];

function relativeTime(date: Date): string {
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function statusLabel(s: AgentStatus) {
  if (s === "certified") return { text: "Certified ✓", cls: "text-green-400" };
  if (s === "pending") return { text: "Pending", cls: "text-yellow-400" };
  return { text: "Failed ✗", cls: "text-red-400" };
}

function topCategory(cats: ExplorerAgent["score"]["categories"]): string {
  const entries = Object.entries(cats) as [string, number][];
  const best = entries.reduce((a, b) => (b[1] > a[1] ? b : a));
  return `${best[0].charAt(0).toUpperCase() + best[0].slice(1)}: ${best[1].toFixed(2)}`;
}

export default function ExplorerPage() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterStatus>("all");
  const [sort, setSort] = useState<SortKey>("score-desc");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    let list = mockAgents;

    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (a) =>
          a.agent.name.toLowerCase().includes(q) ||
          a.agent.id.toLowerCase().includes(q)
      );
    }

    if (filter !== "all") {
      list = list.filter((a) => a.status === filter);
    }

    list = [...list].sort((a, b) => {
      switch (sort) {
        case "score-desc": return b.score.overall - a.score.overall;
        case "score-asc": return a.score.overall - b.score.overall;
        case "recent": return b.lastChecked.getTime() - a.lastChecked.getTime();
        case "name-az": return a.agent.name.localeCompare(b.agent.name);
      }
    });

    return list;
  }, [search, filter, sort]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage = Math.min(page, totalPages);
  const paginated = filtered.slice((safePage - 1) * ITEMS_PER_PAGE, safePage * ITEMS_PER_PAGE);
  const showStart = filtered.length === 0 ? 0 : (safePage - 1) * ITEMS_PER_PAGE + 1;
  const showEnd = Math.min(safePage * ITEMS_PER_PAGE, filtered.length);

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-6 max-w-6xl mx-auto pb-20">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Trust Explorer</h1>
          <p className="text-zinc-400 mt-1">Browse and search all checked agents</p>
        </div>

        {/* Search */}
        <Input
          className="mb-6"
          placeholder="Search agents by name, ID, or capability…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />

        {/* Filters + Sort */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
          <div className="flex flex-wrap gap-2">
            {filters.map((f) => (
              <button
                key={f.key}
                onClick={() => { setFilter(f.key); setPage(1); }}
                className={`px-4 py-1.5 rounded-full text-sm font-medium border transition-all duration-200 ${
                  filter === f.key
                    ? "bg-isnad-teal/20 text-isnad-teal border-isnad-teal/40"
                    : "bg-white/5 text-zinc-400 border-white/10 hover:border-white/20"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-sm text-zinc-300 focus:outline-none focus:ring-2 focus:ring-isnad-teal/50"
          >
            {sorts.map((s) => (
              <option key={s.key} value={s.key} className="bg-zinc-900">
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {/* Desktop Table */}
        <div className="hidden md:block">
          <Card className="p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--card-border)] text-zinc-400">
                  <th className="text-left px-6 py-4 font-medium">Agent</th>
                  <th className="text-left px-6 py-4 font-medium">Score</th>
                  <th className="text-left px-6 py-4 font-medium">Status</th>
                  <th className="text-left px-6 py-4 font-medium">Top Category</th>
                  <th className="text-right px-6 py-4 font-medium">Last Checked</th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence mode="popLayout">
                  {paginated.map((a, i) => (
                    <motion.tr
                      key={a.agent.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ delay: i * 0.04 }}
                      className="border-b border-[var(--card-border)] last:border-0 hover:bg-white/5 transition-colors"
                    >
                      <td className="px-6 py-4">
                        <Link href={`/check/${a.agent.id}`} className="group">
                          <span className="font-semibold text-[var(--foreground)] group-hover:text-isnad-teal transition-colors">
                            {a.agent.name}
                          </span>
                          <span className="block text-xs text-zinc-500 font-mono mt-0.5">
                            {a.agent.id}
                          </span>
                        </Link>
                      </td>
                      <td className="px-6 py-4">
                        <Badge score={a.score.overall}>{a.score.overall}</Badge>
                      </td>
                      <td className={`px-6 py-4 font-medium ${statusLabel(a.status).cls}`}>
                        {statusLabel(a.status).text}
                      </td>
                      <td className="px-6 py-4 text-zinc-300 text-xs">
                        {topCategory(a.score.categories)}
                      </td>
                      <td className="px-6 py-4 text-right text-zinc-500">
                        {relativeTime(a.lastChecked)}
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="px-6 py-16 text-center text-zinc-500">
                No agents found matching your search
              </div>
            )}
          </Card>
        </div>

        {/* Mobile Cards */}
        <div className="md:hidden grid gap-4">
          <AnimatePresence mode="popLayout">
            {paginated.map((a, i) => (
              <motion.div
                key={a.agent.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ delay: i * 0.06 }}
              >
                <Link href={`/check/${a.agent.id}`}>
                  <Card className="flex flex-col gap-3 active:scale-[0.98] transition-transform">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-semibold text-[var(--foreground)]">{a.agent.name}</span>
                        <span className="block text-xs text-zinc-500 font-mono mt-0.5">{a.agent.id}</span>
                      </div>
                      <Badge score={a.score.overall}>{a.score.overall}</Badge>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className={`font-medium ${statusLabel(a.status).cls}`}>
                        {statusLabel(a.status).text}
                      </span>
                      <span className="text-zinc-500 text-xs">{relativeTime(a.lastChecked)}</span>
                    </div>
                    <div className="text-xs text-zinc-400">{topCategory(a.score.categories)}</div>
                  </Card>
                </Link>
              </motion.div>
            ))}
          </AnimatePresence>
          {filtered.length === 0 && (
            <div className="py-16 text-center text-zinc-500">
              No agents found matching your search
            </div>
          )}
        </div>

        {/* Pagination */}
        {filtered.length > 0 && (
          <div className="mt-8 flex items-center justify-between">
            <p className="text-sm text-zinc-500">
              Showing {showStart}-{showEnd} of {filtered.length} agents
            </p>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                disabled={safePage <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={safePage >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
