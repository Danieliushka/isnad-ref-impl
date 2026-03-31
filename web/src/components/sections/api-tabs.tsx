'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';

const tabs = [
  {
    label: 'cURL',
    code: `curl https://isnad.site/api/v1/check/gpt-4-assistant`,
  },
  {
    label: 'Python',
    code: `import requests

response = requests.get("https://isnad.site/api/v1/check/gpt-4-assistant")
result = response.json()

print(f"Score: {result['overall_score']}")
print(f"Certified: {result['certified']}")`,
  },
  {
    label: 'JavaScript',
    code: `const res = await fetch("https://isnad.site/api/v1/check/gpt-4-assistant");

const result = await res.json();
console.log(\`Score: \${result.overall_score}\`);
console.log(\`Certified: \${result.certified}\`);`,
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
            Start with a public trust check, then expand into profile and badge flows
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
