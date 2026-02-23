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
