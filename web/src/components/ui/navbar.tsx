"use client";

import Link from "next/link";
import { motion } from "framer-motion";

const links = [
  { href: "/check", label: "Check" },
  { href: "/explorer", label: "Explorer" },
  { href: "/register", label: "Register" },
  { href: "/docs", label: "Docs" },
  { href: "https://github.com/Danieliushka/isnad-ref-impl", label: "GitHub", external: true },
];

export function Navbar() {
  return (
    <motion.nav
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      className="fixed top-4 left-4 right-4 z-50"
    >
      <div className="max-w-5xl mx-auto bg-white/[0.03] backdrop-blur-2xl border border-white/[0.06] rounded-2xl">
        <div className="px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-1.5">
            <span className="text-lg font-bold tracking-tight text-white">isnad</span>
            <span className="w-1.5 h-1.5 rounded-full bg-isnad-teal" />
          </Link>

          <div className="flex items-center gap-1">
            {links.map((link) =>
              link.external ? (
                <a
                  key={link.href}
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-1.5 text-sm text-zinc-500 hover:text-zinc-200 rounded-lg hover:bg-white/[0.04] transition-all duration-200"
                >
                  {link.label}
                </a>
              ) : (
                <Link
                  key={link.href}
                  href={link.href}
                  className="px-3 py-1.5 text-sm text-zinc-500 hover:text-zinc-200 rounded-lg hover:bg-white/[0.04] transition-all duration-200"
                >
                  {link.label}
                </Link>
              )
            )}
          </div>
        </div>
      </div>
    </motion.nav>
  );
}
