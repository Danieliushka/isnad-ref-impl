import type { Metadata } from 'next';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8420/api/v1';

function getTrustTier(score: number): string {
  if (score >= 80) return 'Certified';
  if (score >= 60) return 'Trusted';
  if (score >= 40) return 'Established';
  if (score >= 20) return 'Emerging';
  return 'New';
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;

  let name = id;
  let description = `Trust profile for AI agent ${id} on isnad Trust Network`;
  let score = 0;
  let tier = 'New';

  try {
    const res = await fetch(`${API_URL}/agents/${id}`, {
      next: { revalidate: 300 },
    });
    if (res.ok) {
      const agent = await res.json();
      name = agent.name || id;
      score = Math.round(agent.trust_score ?? 0);
      tier = getTrustTier(score);
      description =
        agent.description?.slice(0, 160) ||
        `${name} — ${tier} agent on isnad Trust Network. Score: ${score}/100.`;
    }
  } catch {
    // fallback defaults
  }

  const title = `${name} — Trust Score ${score}/100 | isnad`;
  const ogImageUrl = `https://isnad.site/api/og/${id}`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      url: `https://isnad.site/agents/${id}`,
      siteName: 'isnad',
      type: 'profile',
      images: [
        {
          url: ogImageUrl,
          width: 1200,
          height: 630,
          alt: `${name} Trust Score: ${score}/100`,
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [ogImageUrl],
    },
    other: {
      // Embeddable badge URL for external platforms
      'isnad:badge': `https://isnad.site/api/v1/badge/${id}`,
      'isnad:score': String(score),
      'isnad:tier': tier,
    },
  };
}

export default function AgentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
