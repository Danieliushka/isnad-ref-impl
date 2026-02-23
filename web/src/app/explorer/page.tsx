"use client";

import { Navbar } from "@/components/ui/navbar";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useState } from "react";
import Link from "next/link";

const mockAgents = [
  { id: "gpt-4-assistant", name: "GPT-4 Assistant", score: 92, attestations: 47, status: "Certified", checked: "2 min ago" },
  { id: "claude-3-opus", name: "Claude 3 Opus", score: 88, attestations: 34, status: "Certified", checked: "5 min ago" },
  { id: "defi-trader-v3", name: "DeFi Trader v3", score: 73, attestations: 21, status: "Verified", checked: "8 min ago" },
  { id: "support-agent-7", name: "Support Agent 7", score: 85, attestations: 29, status: "Certified", checked: "15 min ago" },
  { id: "trading-bot-v2", name: "Trading Bot v2", score: 67, attestations: 15, status: "Under Review", checked: "22 min ago" },
  { id: "code-reviewer-ai", name: "Code Reviewer AI", score: 91, attestations: 52, status: "Certified", checked: "30 min ago" },
  { id: "data-scraper-x", name: "Data Scraper X", score: 41, attestations: 8, status: "Flagged", checked: "1 hr ago" },
  { id: "research-agent-alpha", name: "Research Agent α", score: 79, attestations: 19, status: "Verified", checked: "2 hr ago" },
];

function statusColor(status: string) {
  if (status === "Certified") return "text-emerald-400";
  if (status === "Verified") return "text-blue-400";
  if (status === "Under Review") return "text-yellow-400";
  return "text-red-400";
}

export default function ExplorerPage() {
  const [search, setSearch] = useState("");

  const filtered = mockAgents.filter(
    (a) =>
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-6 max-w-6xl mx-auto pb-20">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-bold">Trust Explorer</h1>
            <p className="text-zinc-400 mt-1">Browse verified AI agents and their trust scores</p>
          </div>
          <Input
            className="w-full md:w-72"
            placeholder="Search agents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--card-border)] text-zinc-400">
                  <th className="text-left px-6 py-4 font-medium">Agent</th>
                  <th className="text-left px-6 py-4 font-medium">Score</th>
                  <th className="text-left px-6 py-4 font-medium">Attestations</th>
                  <th className="text-left px-6 py-4 font-medium">Status</th>
                  <th className="text-right px-6 py-4 font-medium">Last Checked</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr
                    key={a.id}
                    className="border-b border-[var(--card-border)] last:border-0 hover:bg-white/5 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <Link
                        href={`/check/${a.id}`}
                        className="font-mono text-isnad-teal hover:underline"
                      >
                        {a.id}
                      </Link>
                      <div className="text-xs text-zinc-500 mt-0.5">{a.name}</div>
                    </td>
                    <td className="px-6 py-4">
                      <Badge score={a.score}>{a.score}</Badge>
                    </td>
                    <td className="px-6 py-4 text-zinc-300">{a.attestations}</td>
                    <td className={`px-6 py-4 font-medium ${statusColor(a.status)}`}>
                      {a.status}
                    </td>
                    <td className="px-6 py-4 text-right text-zinc-500">{a.checked}</td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center text-zinc-500">
                      No agents found matching &ldquo;{search}&rdquo;
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="mt-6 text-center text-sm text-zinc-500">
          Showing {filtered.length} of {mockAgents.length} agents · Data updates every 30 seconds
        </div>
      </main>
    </>
  );
}
