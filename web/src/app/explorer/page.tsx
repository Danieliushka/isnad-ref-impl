import { Navbar } from "@/components/ui/navbar";
import { Card } from "@/components/ui/card";

export default function ExplorerPage() {
  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-6 max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Trust Explorer</h1>
        <Card>
          <p className="text-[var(--foreground)]/50">
            Browse and search verified AI agents. Coming soon.
          </p>
        </Card>
      </main>
    </>
  );
}
