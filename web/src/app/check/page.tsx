'use client';

import { Navbar } from '@/components/ui/navbar';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { recentlyChecked } from '@/lib/mock-data';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';

export default function CheckPage() {
  const [agentId, setAgentId] = useState('');
  const router = useRouter();

  function handleCheck() {
    if (agentId.trim()) {
      router.push(`/check/${encodeURIComponent(agentId.trim())}`);
    }
  }

  return (
    <>
      <Navbar />
      <main className="min-h-screen flex flex-col items-center justify-center px-6">
        <motion.div
          className="w-full max-w-2xl"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          {/* Logo / title */}
          <div className="text-center mb-10">
            <motion.div
              className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-isnad-teal/10 border border-isnad-teal/20 mb-6"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', delay: 0.2 }}
            >
              <svg width="32" height="32" viewBox="0 0 20 20" fill="none">
                <path d="M10 2L3 6v5c0 4 3 7 7 8 4-1 7-4 7-8V6L10 2z" stroke="#00d4aa" strokeWidth="1.5" fill="none" />
                <path d="M7 10l2 2 4-4" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </motion.div>
            <h1 className="text-4xl font-bold mb-3">Check Agent Trust</h1>
            <p className="text-zinc-400 text-lg">
              Verify the trust score, attestation chain, and risk profile of any AI agent.
            </p>
          </div>

          {/* Search input */}
          <Card className="p-8">
            <div className="flex flex-col sm:flex-row gap-3">
              <Input
                placeholder="Enter agent ID, name, or public key..."
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCheck()}
                className="text-lg py-4"
              />
              <Button onClick={handleCheck} size="lg" className="whitespace-nowrap">
                Check Trust
              </Button>
            </div>
          </Card>

          {/* Recently checked */}
          <motion.div
            className="mt-10"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
          >
            <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-wider mb-4 text-center">
              Recently Checked
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {recentlyChecked.slice(0, 4).map((agent: { id: string; name: string; score: number }, i: number) => (
                <motion.div
                  key={agent.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.5 + i * 0.1 }}
                >
                  <Card
                    className="p-4 cursor-pointer hover:scale-[1.02] transition-transform text-center"
                    onClick={() => router.push(`/check/${agent.id}`)}
                  >
                    <p className="font-medium text-sm mb-2">{agent.name}</p>
                    <Badge score={agent.score}>{agent.score}</Badge>
                  </Card>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      </main>
    </>
  );
}
