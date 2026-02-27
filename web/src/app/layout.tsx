import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Syne } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

const syne = Syne({
  variable: "--font-syne",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "isnad — Trust Infrastructure for AI Agents",
  description:
    "Verify, certify, and build trust for AI agents with cryptographic attestations and behavioral analysis.",
  keywords: ["AI agents", "trust verification", "cryptographic identity", "attestation", "agent trust score", "isnad"],
  authors: [{ name: "isnad" }],
  openGraph: {
    title: "isnad — Trust Infrastructure for AI Agents",
    description: "Cryptographic verification, behavioral analysis, and attestation chains for AI agents.",
    url: "https://isnad.site",
    siteName: "isnad",
    type: "website",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "isnad — Trust Infrastructure for AI Agents",
    description: "Cryptographic verification, behavioral analysis, and attestation chains for AI agents.",
  },
  metadataBase: new URL("https://isnad.site"),
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} ${syne.variable} font-sans antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
