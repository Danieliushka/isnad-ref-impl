'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';

const tabs = [
  {
    label: 'cURL',
    code: `curl -X POST https://api.isnad.dev/v1/check \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"agent_id": "agent:example:gpt-4"}'`,
  },
  {
    label: 'Python',
    code: `from isnad import IsnadClient

client = IsnadClient(api_key="YOUR_API_KEY")
result = client.check("agent:example:gpt-4")

print(f"Score: {result.score.overall}")
print(f"Certified: {result.agent.is_certified}")`,
  },
  {
    label: 'JavaScript',
    code: `const res = await fetch("https://api.isnad.dev/v1/check", {
  method: "POST",
  headers: {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ agent_id: "agent:example:gpt-4" }),
});

const { score, agent } = await res.json();
console.log(\`Score: \${score.overall}\`);`,
  },
];

export default function ApiTabs() {
  const [active, setActive] = useState(0);

  return (
    <section id="api" className="py-24 px-6">
      <div className="max-w-3xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-12"
        >
          <h2 className="font-heading text-3xl md:text-4xl font-bold tracking-tight mb-4">
            Integrate in Minutes
          </h2>
          <p className="text-zinc-500">
            REST API, Python SDK, or plain cURL — your choice
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          {/* Tab buttons */}
          <div className="flex gap-1 mb-1 px-1">
            {tabs.map((t, i) => (
              <button
                key={t.label}
                onClick={() => setActive(i)}
                className={`relative px-4 py-2 text-xs font-mono tracking-wide rounded-t-lg transition-all duration-200 cursor-pointer ${
                  active === i
                    ? 'text-isnad-teal bg-[#0c0d12]'
                    : 'text-zinc-600 hover:text-zinc-400'
                }`}
              >
                {t.label}
                {active === i && (
                  <motion.div
                    layoutId="activeTab"
                    className="absolute bottom-0 left-0 right-0 h-px bg-isnad-teal"
                    transition={{ duration: 0.2 }}
                  />
                )}
              </button>
            ))}
          </div>

          {/* Code block */}
          <div className="relative bg-[#0c0d12] border border-white/[0.06] rounded-xl rounded-tl-none overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-isnad-teal/40 via-accent/20 to-transparent" />
            <pre className="p-6 overflow-x-auto">
              <code className="text-sm font-mono text-zinc-400 leading-relaxed">
                {tabs[active].code}
              </code>
            </pre>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
