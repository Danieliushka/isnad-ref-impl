import AnimatedSection from './animated-section';

export default function WhyTrustMatters() {
  return (
    <AnimatedSection id="why-trust" className="py-24 px-4 sm:px-6">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-10">
          <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-isnad-teal/60 mb-3 block">
            The Problem
          </span>
          <h2 className="font-heading text-3xl md:text-4xl font-bold tracking-tight">
            Why Trust Matters
          </h2>
        </div>
        <div className="space-y-6 text-zinc-400 text-sm leading-relaxed">
          <p>
            AI agents are entering the economy at scale — negotiating contracts, managing funds,
            executing tasks on behalf of humans and other agents. Yet there is no standard way to
            verify whether an agent is who it claims to be, whether it has a track record of
            delivering on promises, or whether it has been compromised.
          </p>
          <p>
            Without verifiable trust, every agent interaction is a leap of faith. Platforms can&apos;t
            distinguish reliable agents from malicious ones. Developers can&apos;t build secure
            multi-agent workflows. Users can&apos;t delegate with confidence. The agent economy
            stalls before it starts.
          </p>
          <p>
            <span className="text-isnad-teal font-medium">isnad</span> solves this with
            cryptographic identity, attestation chains, and behavioral scoring — giving every
            agent a verifiable reputation that travels across platforms. No central authority.
            No blind trust. Just math.
          </p>
        </div>
      </div>
    </AnimatedSection>
  );
}
