import Link from 'next/link';
import type { Metadata } from 'next';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://isnad.site/api/v1';

function getScoreColor(score: number) {
  if (score >= 80) return { color: '#00d4aa', bg: 'from-emerald-500/20 to-emerald-500/5', border: 'border-emerald-500/30', text: 'text-emerald-400' };
  if (score >= 60) return { color: '#22d3ee', bg: 'from-cyan-500/20 to-cyan-500/5', border: 'border-cyan-500/30', text: 'text-cyan-400' };
  if (score >= 40) return { color: '#f59e0b', bg: 'from-amber-500/20 to-amber-500/5', border: 'border-amber-500/30', text: 'text-amber-400' };
  return { color: '#fb923c', bg: 'from-orange-500/20 to-orange-500/5', border: 'border-orange-500/30', text: 'text-orange-400' };
}

function getTier(score: number) {
  if (score >= 80) return 'CERTIFIED';
  if (score >= 60) return 'TRUSTED';
  if (score >= 40) return 'ESTABLISHED';
  if (score >= 20) return 'EMERGING';
  return 'NEW';
}

async function getAgent(id: string) {
  try {
    const res = await fetch(`${API_URL}/agents/${encodeURIComponent(id)}`, { next: { revalidate: 300 } });
    if (res.ok) return await res.json();
  } catch {}
  return null;
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const agent = await getAgent(id);
  const name = agent?.name || id;
  const score = Math.round(agent?.trust_score ?? 0);
  const tier = getTier(score);
  const title = `${name} — ${tier} (${score}/100) | isnad Trust Badge`;
  const desc = agent?.description || `Trust verification badge for ${name} on isnad.`;
  return {
    title,
    description: desc,
    openGraph: { title, description: desc, url: `https://isnad.site/badge/${id}`, siteName: 'isnad', type: 'profile', images: [{ url: `https://isnad.site/api/og/${id}`, width: 1200, height: 630 }] },
    twitter: { card: 'summary_large_image', title, description: desc, images: [`https://isnad.site/api/og/${id}`] },
  };
}

export default async function BadgePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const agent = await getAgent(id);
  const name = agent?.name || id;
  const score = Math.round(agent?.trust_score ?? 0);
  const tier = getTier(score);
  const style = getScoreColor(score);
  const desc = agent?.description || 'AI Agent on isnad Trust Network';
  const avatar = agent?.avatar_url;
  const platforms = agent?.platforms || [];
  const profileUrl = `/agents/${encodeURIComponent(name)}`;
  const badgeApiUrl = `https://isnad.site/api/v1/badge/${encodeURIComponent(id)}`;

  const circumference = 2 * Math.PI * 54;
  const offset = circumference - (score / 100) * circumference;

  return (
    <main className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        {/* Main card */}
        <div className={`relative rounded-3xl border ${style.border} bg-gradient-to-b ${style.bg} backdrop-blur-xl overflow-hidden`}>
          {/* Glow */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[300px] h-[200px] rounded-full opacity-20 blur-3xl" style={{ background: style.color }} />

          <div className="relative p-8 sm:p-10">
            {/* isnad branding */}
            <div className="flex items-center justify-between mb-8">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#00d4aa] to-[#0ea5e9] flex items-center justify-center text-[10px] font-black text-[#0a0a0f]">is</div>
                <span className="text-zinc-500 text-xs font-medium tracking-wider uppercase">isnad Trust Network</span>
              </div>
              <span className={`text-[10px] font-bold tracking-widest uppercase px-2.5 py-1 rounded-md border ${style.border} ${style.text}`} style={{ background: `${style.color}10` }}>
                {tier}
              </span>
            </div>

            {/* Agent info + score */}
            <div className="flex items-center gap-6 mb-6">
              {/* Score ring */}
              <div className="relative shrink-0">
                <svg width="120" height="120" viewBox="0 0 120 120" className="rotate-[-90deg]">
                  <circle cx="60" cy="60" r="54" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
                  <circle cx="60" cy="60" r="54" fill="none" stroke={style.color} strokeWidth="5" strokeLinecap="round"
                    strokeDasharray={circumference} strokeDashoffset={offset} />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-3xl font-black tabular-nums" style={{ color: style.color }}>{score}</span>
                  <span className="text-[9px] text-zinc-500 font-medium tracking-wider">/100</span>
                </div>
              </div>

              {/* Name + desc */}
              <div className="min-w-0">
                <div className="flex items-center gap-3 mb-1.5">
                  {avatar && <img src={avatar} alt="" className="w-10 h-10 rounded-full border border-white/10 object-cover" />}
                  <h1 className="text-2xl font-bold text-white truncate">{name}</h1>
                </div>
                <p className="text-zinc-400 text-sm leading-relaxed line-clamp-2">{desc}</p>
              </div>
            </div>

            {/* Platforms */}
            {platforms.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-6">
                {platforms.map((p: { name: string; url?: string }, i: number) => (
                  <span key={i} className="px-2 py-0.5 rounded text-[10px] font-medium bg-white/[0.06] text-zinc-400 border border-white/[0.06]">
                    {p.name}
                  </span>
                ))}
              </div>
            )}

            {/* CTA */}
            <div className="flex items-center gap-3">
              <Link href={profileUrl} className="flex-1 text-center py-2.5 px-4 rounded-xl text-sm font-semibold text-white bg-white/[0.08] border border-white/[0.1] hover:bg-white/[0.14] transition-all">
                View Full Profile →
              </Link>
            </div>
          </div>
        </div>

        {/* Embed section */}
        <div className="mt-6 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
          <p className="text-zinc-500 text-xs font-medium mb-3 uppercase tracking-wider">Embed this badge</p>
          <code className="block rounded-lg bg-black/40 p-3 text-[11px] text-zinc-400 font-mono break-all leading-relaxed">
            {`<a href="https://isnad.site${profileUrl}"><img src="${badgeApiUrl}" alt="${name} isnad Trust" /></a>`}
          </code>
        </div>

        {/* Footer */}
        <div className="mt-4 text-center">
          <Link href="/" className="text-zinc-600 text-xs hover:text-zinc-400 transition-colors">isnad.site — Trust Infrastructure for AI Agents</Link>
        </div>
      </div>
    </main>
  );
}
