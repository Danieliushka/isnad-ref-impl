"use client";

import { Navbar } from "@/components/ui/navbar";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import TrustScoreRing from "@/components/trust-score-ring";
import RadarChart from "@/components/radar-chart";
import { useParams } from "next/navigation";

// Mock data — will be replaced with API call
const mockReport = {
  overall_score: 82,
  confidence: "high" as const,
  risk_flags: ["Behavioral anomaly detected in last 24h"],
  attestation_count: 34,
  last_checked: new Date().toISOString(),
  categories: [
    { name: "Identity", score: 95, modules_passed: 6, modules_total: 6, findings: [] },
    { name: "Behavior", score: 72, modules_passed: 5, modules_total: 6, findings: ["Minor anomaly in response pattern"] },
    { name: "Provenance", score: 88, modules_passed: 5, modules_total: 6, findings: [] },
    { name: "Security", score: 91, modules_passed: 6, modules_total: 6, findings: [] },
    { name: "Compliance", score: 68, modules_passed: 4, modules_total: 6, findings: ["Missing data retention policy"] },
    { name: "Performance", score: 78, modules_passed: 5, modules_total: 6, findings: [] },
  ],
  certified: true,
  certification_id: "cert-2026-02-23-a8f3",
};

function confidenceColor(c: string) {
  if (c === "high") return "text-emerald-400";
  if (c === "medium") return "text-yellow-400";
  return "text-red-400";
}

function categoryBarColor(score: number) {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 60) return "bg-yellow-500";
  return "bg-red-500";
}

export default function TrustReportPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? decodeURIComponent(params.id) : "unknown";
  const report = mockReport;
  const radarCategories = report.categories.map((c) => ({ label: c.name, value: c.score / 100 }));

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-6 max-w-5xl mx-auto pb-20">
        {/* Header */}
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-bold">Trust Report</h1>
            <p className="font-mono text-isnad-teal text-lg mt-1">{id}</p>
          </div>
          {report.certified && (
            <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-4 py-2">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M10 2L3 6v5c0 4 3 7 7 8 4-1 7-4 7-8V6L10 2z" stroke="#10b981" strokeWidth="1.5" fill="none" />
                <path d="M7 10l2 2 4-4" stroke="#10b981" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="text-emerald-400 text-sm font-medium">Certified</span>
              <span className="text-zinc-500 text-xs font-mono">{report.certification_id}</span>
            </div>
          )}
        </div>

        {/* Score + Radar */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <Card className="flex flex-col items-center justify-center py-8">
            <TrustScoreRing score={report.overall_score} size={180} />
            <div className="mt-4 text-center">
              <div className="text-sm text-zinc-400">
                Confidence:{" "}
                <span className={`font-medium ${confidenceColor(report.confidence)}`}>
                  {report.confidence}
                </span>
              </div>
              <div className="text-sm text-zinc-400 mt-1">
                {report.attestation_count} attestations verified
              </div>
            </div>
          </Card>

          <Card className="flex items-center justify-center py-8">
            <RadarChart categories={radarCategories} size={280} />
          </Card>
        </div>

        {/* Risk Flags */}
        {report.risk_flags.length > 0 && (
          <Card className="mb-6 border-yellow-500/30 bg-yellow-500/5">
            <h2 className="text-lg font-semibold text-yellow-400 mb-3">⚠ Risk Flags</h2>
            <ul className="space-y-1">
              {report.risk_flags.map((flag, i) => (
                <li key={i} className="text-sm text-zinc-300 flex items-start gap-2">
                  <span className="text-yellow-400 mt-0.5">•</span>
                  {flag}
                </li>
              ))}
            </ul>
          </Card>
        )}

        {/* Category Breakdown */}
        <Card>
          <h2 className="text-lg font-semibold mb-6">Category Breakdown</h2>
          <div className="space-y-4">
            {report.categories.map((cat) => (
              <div key={cat.name}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-3">
                    <span className="font-medium text-sm">{cat.name}</span>
                    <span className="text-xs text-zinc-500">
                      {cat.modules_passed}/{cat.modules_total} modules
                    </span>
                  </div>
                  <Badge score={cat.score}>{cat.score}</Badge>
                </div>
                <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${categoryBarColor(cat.score)}`}
                    style={{ width: `${cat.score}%` }}
                  />
                </div>
                {cat.findings.length > 0 && (
                  <div className="mt-1.5 text-xs text-zinc-500">
                    {cat.findings.map((f, i) => (
                      <span key={i}>↳ {f}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>

        {/* Metadata */}
        <div className="mt-6 text-center text-sm text-zinc-500">
          Last checked: {new Date(report.last_checked).toLocaleString()} · Report generated by isnad v0.3.0
        </div>
      </main>
    </>
  );
}
