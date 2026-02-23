import { Navbar } from "@/components/ui/navbar";
import { Card } from "@/components/ui/card";

export default function DocsPage() {
  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-6 max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">API Documentation</h1>
        <Card>
          <p className="text-[var(--foreground)]/50">
            API reference and integration guides. Coming soon.
          </p>
        </Card>
      </main>
    </>
  );
}
