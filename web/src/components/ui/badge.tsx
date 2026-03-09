import type { ReactNode } from "react";

type BadgeVariant = "default" | "success" | "warning" | "danger";

interface BadgeProps {
  variant?: BadgeVariant;
  score?: number;
  children?: ReactNode;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
  success: "bg-green-500/20 text-green-400 border-green-500/30",
  warning: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  danger: "bg-red-500/20 text-red-400 border-red-500/30",
};

function getScoreVariant(score: number): BadgeVariant {
  if (score >= 80) return "success";
  if (score >= 60) return "warning";
  return "danger";
}

export function Badge({ variant, score, children, className = "" }: BadgeProps) {
  const v = variant ?? (score !== undefined ? getScoreVariant(score) : "default");
  return (
    <span
      className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium border ${variantStyles[v]} ${className}`}
    >
      {children ?? score}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Trust Level Badge — larger, with gradient + icons + glow animation */
/* ------------------------------------------------------------------ */

export type TrustLevel = "new" | "emerging" | "established" | "trusted" | "certified";

function getTrustLevel(score: number): TrustLevel {
  if (score >= 80) return "certified";
  if (score >= 60) return "trusted";
  if (score >= 40) return "established";
  if (score >= 20) return "emerging";
  return "new";
}

function getTrustLevelLabel(level: TrustLevel): string {
  switch (level) {
    case "new": return "New";
    case "emerging": return "Emerging";
    case "established": return "Established";
    case "trusted": return "Trusted";
    case "certified": return "Certified";
  }
}

const trustLevelStyles: Record<TrustLevel, { gradient: string; text: string; glow: string; icon: string }> = {
  "new": {
    gradient: "from-zinc-600/30 to-zinc-500/20",
    text: "text-zinc-300",
    glow: "",
    icon: "○",
  },
  emerging: {
    gradient: "from-amber-500/25 to-yellow-500/15",
    text: "text-amber-300",
    glow: "shadow-[0_0_12px_rgba(245,158,11,0.2)]",
    icon: "◑",
  },
  established: {
    gradient: "from-blue-500/25 to-cyan-500/15",
    text: "text-blue-300",
    glow: "shadow-[0_0_14px_rgba(59,130,246,0.2)]",
    icon: "◉",
  },
  trusted: {
    gradient: "from-emerald-500/25 to-green-500/15",
    text: "text-emerald-300",
    glow: "shadow-[0_0_16px_rgba(16,185,129,0.25)]",
    icon: "◉",
  },
  certified: {
    gradient: "from-isnad-teal/30 to-amber-500/15",
    text: "text-isnad-teal",
    glow: "shadow-[0_0_24px_rgba(0,212,170,0.3)]",
    icon: "★",
  },
};

interface TrustBadgeProps {
  score: number;
  className?: string;
}

export function TrustBadge({ score, className = "" }: TrustBadgeProps) {
  const level = getTrustLevel(score);
  const style = trustLevelStyles[level];
  const label = getTrustLevelLabel(level);

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border border-white/[0.1] bg-gradient-to-r ${style.gradient} ${style.text} ${style.glow} ${className}`}
    >
      <span className="text-[11px]">{style.icon}</span>
      {label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* TrustBadgeLarge — for agent detail page, with shimmer animation    */
/* ------------------------------------------------------------------ */

interface TrustBadgeLargeProps {
  score: number;
  className?: string;
}

export function TrustBadgeLarge({ score, className = "" }: TrustBadgeLargeProps) {
  const level = getTrustLevel(score);
  const style = trustLevelStyles[level];
  const label = getTrustLevelLabel(level);

  return (
    <div
      className={`relative inline-flex items-center gap-3 px-6 py-3 rounded-2xl text-base font-bold border border-white/[0.12] bg-gradient-to-r ${style.gradient} ${style.text} ${style.glow} overflow-hidden ${className}`}
    >
      {/* Shimmer overlay */}
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_3s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-white/[0.06] to-transparent" />

      {/* Shield / star icon */}
      <span className="text-xl relative z-10">
        {level === "certified" ? "🛡️" : level === "trusted" ? "✦" : level === "established" ? "◉" : level === "emerging" ? "◐" : "○"}
      </span>

      <div className="relative z-10 flex flex-col">
        <span className="text-sm font-bold tracking-wide">{label}</span>
        <span className="text-[10px] font-medium opacity-60 uppercase tracking-widest">
          Score: {score}/100
        </span>
      </div>
    </div>
  );
}
