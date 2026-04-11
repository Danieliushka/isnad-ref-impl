import { ImageResponse } from 'next/og';
import { NextRequest } from 'next/server';

export const runtime = 'nodejs';

function getScoreColor(score: number): string {
  if (score >= 80) return '#00d4aa';
  if (score >= 50) return '#f59e0b';
  if (score >= 21) return '#fb923c';
  return '#ef4444';
}

function getTrustTier(score: number): string {
  if (score >= 80) return 'CERTIFIED';
  if (score >= 60) return 'TRUSTED';
  if (score >= 40) return 'ESTABLISHED';
  if (score >= 20) return 'EMERGING';
  return 'NEW';
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  // Fetch agent data from our API
  let agent: {
    name: string;
    description?: string;
    agent_type?: string;
    trust_score?: number;
    platforms?: { name: string }[];
    capabilities?: string[];
  } = { name: id };

  try {
    const API = process.env.NEXT_PUBLIC_API_URL || 'https://isnad.site/api/v1';
    const res = await fetch(`${API}/agents/${id}`, { next: { revalidate: 300 } });
    if (res.ok) agent = await res.json();
  } catch {
    // fallback to defaults
  }

  const score = Math.round(agent.trust_score ?? 0);
  const tier = getTrustTier(score);
  const color = getScoreColor(score);
  const platforms = agent.platforms?.map(p => p.name).join(' · ') || '';
  const desc = agent.description?.slice(0, 120) || 'AI Agent on isnad Trust Network';

  return new ImageResponse(
    (
      <div
        style={{
          width: '1200px',
          height: '630px',
          display: 'flex',
          flexDirection: 'column',
          background: 'linear-gradient(135deg, #0a0a0f 0%, #111118 50%, #0d1117 100%)',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Subtle grid pattern */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            opacity: 0.03,
            backgroundImage: 'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
            display: 'flex',
          }}
        />

        {/* Glow effect */}
        <div
          style={{
            position: 'absolute',
            top: '-100px',
            right: '-100px',
            width: '400px',
            height: '400px',
            borderRadius: '50%',
            background: `radial-gradient(circle, ${color}15, transparent 70%)`,
            display: 'flex',
          }}
        />

        {/* Content */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            padding: '60px',
            flex: 1,
            justifyContent: 'space-between',
          }}
        >
          {/* Top: isnad branding */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #00d4aa, #0ea5e9)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '18px',
                fontWeight: 800,
                color: '#0a0a0f',
              }}
            >
              is
            </div>
            <span style={{ color: '#52525b', fontSize: '18px', fontWeight: 500, letterSpacing: '0.05em' }}>
              isnad Trust Network
            </span>
          </div>

          {/* Middle: Agent info */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '48px' }}>
            {/* Score circle */}
            <div
              style={{
                width: '180px',
                height: '180px',
                borderRadius: '50%',
                border: `4px solid ${color}`,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                background: `${color}08`,
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: '64px', fontWeight: 800, color, lineHeight: 1 }}>
                {score}
              </span>
              <span style={{ fontSize: '14px', fontWeight: 600, color: '#71717a', letterSpacing: '0.15em', marginTop: '4px' }}>
                {tier}
              </span>
            </div>

            {/* Agent details */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: 1 }}>
              <div style={{ fontSize: '48px', fontWeight: 800, color: '#fafafa', lineHeight: 1.1 }}>
                {agent.name}
              </div>
              <div style={{ fontSize: '20px', color: '#a1a1aa', lineHeight: 1.4, maxWidth: '600px' }}>
                {desc}
              </div>
              {platforms && (
                <div style={{ fontSize: '15px', color: '#52525b', marginTop: '4px' }}>
                  {platforms}
                </div>
              )}
            </div>
          </div>

          {/* Bottom: URL + badge */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '16px', color: '#3f3f46', fontWeight: 500 }}>
              isnad.site/agents/{id}
            </span>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 16px',
                borderRadius: '12px',
                border: `1px solid ${color}30`,
                background: `${color}10`,
              }}
            >
              <span style={{ fontSize: '14px', color }}>
                🛡️ Trust Score: {score}/100
              </span>
            </div>
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
    }
  );
}
