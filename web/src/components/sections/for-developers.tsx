import AnimatedSection from './animated-section';
import { Card } from '@/components/ui/card';

export default function ForDevelopers() {
  return (
    <AnimatedSection id="for-developers" className="py-24 px-4 sm:px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-isnad-teal/60 mb-3 block">
            Integration
          </span>
          <h2 className="font-heading text-3xl md:text-4xl font-bold tracking-tight mb-3">
            For Developers
          </h2>
          <p className="text-zinc-500 text-sm max-w-xl mx-auto">
            Integrate trust verification into your agent platform in minutes. One API call to check any agent.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Check an agent */}
          <Card>
            <h3 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
              Check Agent Trust Score
            </h3>
            <div className="bg-black/40 rounded-xl p-4 overflow-x-auto">
              <pre className="text-xs text-zinc-400 font-mono whitespace-pre leading-relaxed">
{`curl https://isnad.site/api/v1/agents/{agent_id}

# Response:
{
  "agent_id": "fbd068f5-...",
  "name": "Gendolf",
  "trust_score": 42.5,
  "is_certified": false,
  "platforms": [...]
}`}
              </pre>
            </div>
          </Card>

          {/* Register an agent */}
          <Card>
            <h3 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
              Register a New Agent
            </h3>
            <div className="bg-black/40 rounded-xl p-4 overflow-x-auto">
              <pre className="text-xs text-zinc-400 font-mono whitespace-pre leading-relaxed">
{`curl -X POST https://isnad.site/api/v1/agents/register \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "my-agent",
    "description": "Task automation",
    "agent_type": "autonomous",
    "platforms": [],
    "capabilities": ["code"]
  }'`}
              </pre>
            </div>
          </Card>
        </div>

        <div className="mt-8 text-center">
          <a
            href="/docs"
            className="text-isnad-teal/70 hover:text-isnad-teal text-sm font-medium transition-colors"
          >
            Full API documentation →
          </a>
        </div>
      </div>
    </AnimatedSection>
  );
}
