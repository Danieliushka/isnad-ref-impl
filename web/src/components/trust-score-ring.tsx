'use client';

import { motion } from 'framer-motion';

interface TrustScoreRingProps {
  score: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
}

function getColor(score: number): string {
  if (score >= 80) return '#00d4aa';
  if (score >= 60) return '#f59e0b';
  if (score >= 40) return '#f97316';
  return '#ef4444';
}

function getGrade(score: number): string {
  if (score >= 80) return 'CERTIFIED';
  if (score >= 60) return 'TRUSTED';
  if (score >= 40) return 'ESTABLISHED';
  if (score >= 20) return 'EMERGING';
  return 'NEW';
}

export default function TrustScoreRing({
  score,
  size = 200,
  strokeWidth = 6,
  label = 'Trust Score',
}: TrustScoreRingProps) {
  const normalizedScore = Math.max(0, Math.min(100, score));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (normalizedScore / 100) * circumference;
  const color = getColor(normalizedScore);
  const grade = getGrade(normalizedScore);
  const compact = size <= 90;
  const condensed = size <= 150;
  const showGrade = !compact;
  const showLabel = Boolean(label) && size >= 110;
  const scoreFontSize = compact ? Math.round(size * 0.32) : condensed ? Math.round(size * 0.24) : Math.round(size * 0.2);
  const gradeFontSize = condensed ? 10 : 14;
  const labelFontSize = condensed ? 9 : 10;

  return (
    <div
      className="relative inline-flex items-center justify-center shrink-0"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        {/* Background ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.04)"
          strokeWidth={strokeWidth}
        />
        {/* Progress ring */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference - progress }}
          transition={{ duration: 1.5, ease: 'easeOut', delay: 0.3 }}
          style={{ filter: `drop-shadow(0 0 8px ${color}30)` }}
        />
      </svg>
      {/* Center text */}
      <div className="absolute inset-[16%] flex flex-col items-center justify-center rounded-full border border-white/[0.03] bg-[#07090d]/75">
        <motion.span
          className="font-bold font-mono tabular-nums leading-none"
          style={{ color }}
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 1 }}
          aria-label={`Trust score ${normalizedScore}`}
          title={`Trust score ${normalizedScore}`}
        >
          <span style={{ fontSize: scoreFontSize }}>{normalizedScore}</span>
        </motion.span>
        {showGrade && (
          <motion.span
            className="mt-1 font-semibold tracking-[0.18em] uppercase"
            style={{ color, fontSize: gradeFontSize }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.2 }}
          >
            {grade}
          </motion.span>
        )}
        {showLabel && (
          <motion.span
            className="mt-1 uppercase text-zinc-600"
            style={{ fontSize: labelFontSize, letterSpacing: '0.18em' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.4 }}
          >
            {label}
          </motion.span>
        )}
      </div>
    </div>
  );
}
