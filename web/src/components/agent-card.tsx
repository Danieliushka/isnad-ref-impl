'use client';

import Link from 'next/link';
import Image from 'next/image';
import { motion } from 'framer-motion';
import TrustScoreRing from './trust-score-ring';
import { TrustBadge } from '@/components/ui/badge';
import type { AgentProfile } from '@/lib/api';

const typeColors: Record<string, { bg: string; text: string; label: string }> = {
  autonomous: { bg: 'bg-purple-500/15', text: 'text-purple-400', label: 'Autonomous' },
  'tool-calling': { bg: 'bg-blue-500/15', text: 'text-blue-400', label: 'Tool-Calling' },
  'human-supervised': { bg: 'bg-amber-500/15', text: 'text-amber-400', label: 'Human-Supervised' },
};

function getScoreColor(score: number): string {
  if (score >= 80) return '#00d4aa';
  if (score >= 50) return '#f59e0b';
  return '#ef4444';
}

function getActivityStatus(createdAt: string): { color: string; label: string } {
  const now = Date.now();
  const created = new Date(createdAt).getTime();
  const daysSince = (now - created) / (1000 * 60 * 60 * 24);
  if (daysSince < 7) return { color: 'bg-emerald-400', label: 'Active' };
  if (daysSince < 30) return { color: 'bg-yellow-400', label: 'Stale' };
  return { color: 'bg-red-400', label: 'Inactive' };
}

interface AgentCardProps {
  agent: AgentProfile;
  index?: number;
}

export default function AgentCard({ agent, index = 0 }: AgentCardProps) {
  const typeInfo = typeColors[agent.agent_type] || typeColors['autonomous'];
  const activity = getActivityStatus(agent.created_at);
  const score = Math.round(agent.trust_score);
  const scoreColor = getScoreColor(score);

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.08, ease: 'easeOut' }}
    >
      <Link href={`/agents/${agent.agent_id}`}>
        <div
          className="group relative bg-white/[0.03] backdrop-blur-xl border border-white/[0.07] rounded-2xl p-4 sm:p-5 min-h-[180px] sm:min-h-[200px] overflow-hidden transition-all duration-500 hover:border-isnad-teal/25 hover:bg-white/[0.05] hover:shadow-[0_0_60px_-12px_rgba(0,212,170,0.15)] hover:scale-[1.02] cursor-pointer"
        >
          {/* Top row: Avatar + Score ring + Info */}
          <div className="flex items-start gap-4">
            {/* Avatar */}
            <div className="shrink-0">
              {agent.avatar_url ? (
                <img
                  src={agent.avatar_url}
                  alt={agent.name}
                  className="w-10 h-10 rounded-full object-cover border border-white/[0.1]"
                />
              ) : (
                <div className="w-10 h-10 rounded-full bg-white/[0.06] border border-white/[0.1] flex items-center justify-center text-sm font-semibold text-zinc-400">
                  {agent.name.charAt(0).toUpperCase()}
                </div>
              )}
            </div>

            {/* Agent Info */}
            <div className="flex-1 min-w-0">
              {/* Name + Activity dot */}
              <div className="flex items-center gap-2 mb-1.5">
                <h3 className="text-base font-semibold text-white truncate group-hover:text-isnad-teal transition-colors">
                  {agent.name}
                </h3>
                <div className="flex items-center gap-1.5 shrink-0">
                  <div className={`w-2 h-2 rounded-full ${activity.color} shadow-[0_0_6px_currentColor]`} />
                </div>
              </div>

              {/* Type badge + Certified */}
              <div className="flex items-center gap-2 mb-2">
                <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium tracking-wide uppercase ${typeInfo.bg} ${typeInfo.text} border border-current/10`}>
                  {typeInfo.label}
                </span>
                {score > 0 && <TrustBadge score={score} />}
                {agent.is_certified && (
                  <span className="text-[10px] font-medium text-isnad-teal bg-isnad-teal/10 px-2 py-0.5 rounded-full border border-isnad-teal/20">
                    ✓ Certified
                  </span>
                )}
              </div>

              {/* Description */}
              {agent.description ? (
                <p className="text-zinc-500 text-xs line-clamp-2 leading-relaxed">
                  {agent.description}
                </p>
              ) : (
                <p className="text-zinc-600 text-xs italic">No description provided</p>
              )}

              {/* Platforms + Capabilities badges */}
              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                {agent.platforms && agent.platforms.length > 0 && (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono text-zinc-500 bg-white/[0.04] border border-white/[0.06]">
                    {agent.platforms.length} platform{agent.platforms.length !== 1 ? 's' : ''}
                  </span>
                )}
                {agent.capabilities && agent.capabilities.slice(0, 3).map((cap, i) => (
                  <span key={i} className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono text-zinc-500 bg-white/[0.04] border border-white/[0.06]">
                    {cap}
                  </span>
                ))}
                {agent.capabilities && agent.capabilities.length > 3 && (
                  <span className="text-[9px] text-zinc-600 font-mono">+{agent.capabilities.length - 3} more</span>
                )}
              </div>
            </div>

            {/* Trust Score Ring */}
            <div className="shrink-0">
              <TrustScoreRing score={score} size={64} strokeWidth={3} label="" />
            </div>
          </div>

          {/* Hover glow overlay */}
          <div
            className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
            style={{
              background: `radial-gradient(ellipse at 50% 0%, ${scoreColor}08, transparent 70%)`,
            }}
          />
        </div>
      </Link>
    </motion.div>
  );
}
