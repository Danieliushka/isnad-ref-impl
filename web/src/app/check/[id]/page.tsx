import { Navbar } from "@/components/ui/navbar";
import { Card } from "@/components/ui/card";

export default async function TrustReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-6 max-w-4xl mx-auto">
        <Card>
          <h1 className="text-2xl font-bold">
            Trust Report for{" "}
            <span className="text-isnad-teal font-mono">{id}</span>
          </h1>
          <p className="mt-4 text-[var(--foreground)]/50">
            Detailed trust report will be displayed here.
          </p>
        </Card>
      </main>
    </>
  );
}
