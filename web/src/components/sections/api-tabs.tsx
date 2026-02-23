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
    <section className="py-24 px-6">
      <div className="max-w-3xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-10"
        >
          <h2 className="text-3xl md:text-4xl font-bold mb-4">Integrate in Minutes</h2>
          <p className="text-zinc-400">REST API, Python SDK, or plain cURL — your choice</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          <div className="flex gap-1 mb-4">
            {tabs.map((t, i) => (
              <button
                key={t.label}
                onClick={() => setActive(i)}
                className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors ${
                  active === i
                    ? 'bg-isnad-teal text-surface-dark'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/5'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-6 overflow-x-auto">
            <pre className="text-sm font-mono text-zinc-300 leading-relaxed whitespace-pre">
              {tabs[active].code}
            </pre>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
