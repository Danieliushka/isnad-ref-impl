"use client";

import Link from "next/link";
import { ThemeToggle } from "./theme-toggle";

const links = [
  { href: "/check", label: "Check" },
  { href: "/explorer", label: "Explorer" },
  { href: "/docs", label: "Docs" },
  { href: "https://github.com/nickan2c/isnad-ref-impl", label: "GitHub", external: true },
];

export function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-[var(--card-bg)] backdrop-blur-xl border-b border-[var(--card-border)]">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold text-isnad-teal">
          isnad
        </Link>

        <div className="flex items-center gap-6">
          {links.map((link) =>
            link.external ? (
              <a
                key={link.href}
                href={link.href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-[var(--foreground)]/60 hover:text-isnad-teal transition-colors"
              >
                {link.label}
              </a>
            ) : (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-[var(--foreground)]/60 hover:text-isnad-teal transition-colors"
              >
                {link.label}
              </Link>
            )
          )}
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
}
