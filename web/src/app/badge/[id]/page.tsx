import Link from 'next/link';

export default async function BadgePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const badgeUrl = `https://isnad.site/api/v1/badge/${encodeURIComponent(id)}`;
  const profileUrl = `https://isnad.site/agents/${encodeURIComponent(id)}`;
  const embedCode = `<a href="${profileUrl}" target="_blank" rel="noopener noreferrer"><img src="${badgeUrl}" alt="isnad Trust Badge" /></a>`;

  return (
    <main className="min-h-screen bg-[#0a0a0f] text-zinc-100 flex items-center justify-center px-6">
      <div className="w-full max-w-2xl rounded-2xl border border-white/10 bg-white/[0.03] p-8">
        <h1 className="text-2xl font-semibold mb-2">isnad Trust Badge</h1>
        <p className="text-zinc-400 mb-6">Human-friendly preview page. Use this link for people, and API URL for embeds.</p>

        <div className="rounded-xl border border-white/10 bg-black/30 p-6 mb-6 flex items-center justify-center">
          <a href={profileUrl} target="_blank" rel="noopener noreferrer" className="inline-block">
            <img src={badgeUrl} alt="isnad Trust Badge" className="h-8 w-auto" />
          </a>
        </div>

        <div className="space-y-4 text-sm">
          <div>
            <div className="text-zinc-400 mb-1">Public page</div>
            <code className="block rounded bg-black/40 p-2 text-zinc-200 break-all">https://isnad.site/badge/{id}</code>
          </div>
          <div>
            <div className="text-zinc-400 mb-1">API image URL</div>
            <code className="block rounded bg-black/40 p-2 text-zinc-200 break-all">{badgeUrl}</code>
          </div>
          <div>
            <div className="text-zinc-400 mb-1">Embed code</div>
            <code className="block rounded bg-black/40 p-2 text-zinc-200 break-all">{embedCode}</code>
          </div>
        </div>

        <div className="mt-6">
          <Link href={profileUrl} className="text-isnad-teal hover:underline">→ Open agent profile</Link>
        </div>
      </div>
    </main>
  );
}
