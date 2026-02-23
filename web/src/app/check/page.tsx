"use client";

import { Navbar } from "@/components/ui/navbar";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function CheckPage() {
  const [agentId, setAgentId] = useState("");
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
        <Card className="w-full max-w-lg p-8">
          <h1 className="text-2xl font-bold mb-6">Check an Agent</h1>
          <div className="flex gap-3">
            <Input
              placeholder="Enter agent ID or public key..."
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCheck()}
            />
            <Button onClick={handleCheck}>Check</Button>
          </div>
        </Card>
      </main>
    </>
  );
}
