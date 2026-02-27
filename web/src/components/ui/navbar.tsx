"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";

const links = [
  { href: "/check", label: "Check" },
  { href: "/explorer", label: "Explorer" },
  { href: "/register", label: "Register" },
  { href: "/docs", label: "Docs" },
  { href: "https://github.com/Danieliushka/isnad-ref-impl", label: "GitHub", external: true },
];

function NavLink({ link, active }: { link: typeof links[number]; active?: boolean }) {
  const base = "px-3 py-1.5 text-sm rounded-lg transition-all duration-200";
  const cls = active
    ? `${base} text-isnad-teal bg-isnad-teal/[0.08]`
    : `${base} text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.04]`;
  if (link.external) {
    return (
      <a href={link.href} target="_blank" rel="noopener noreferrer" className={cls}>
        {link.label}
      </a>
    );
  }
  return (
    <Link href={link.href} className={cls}>
      {link.label}
    </Link>
  );
}

export function Navbar() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

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

          {/* Desktop links */}
          <div className="hidden sm:flex items-center gap-1">
            {links.map((link) => (
              <NavLink key={link.href} link={link} active={!link.external && pathname === link.href} />
            ))}
          </div>

          {/* Mobile hamburger */}
          <button
            onClick={() => setOpen(!open)}
            className="sm:hidden p-2 text-zinc-400 hover:text-zinc-200 transition-colors"
            aria-label="Toggle menu"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              {open ? (
                <>
                  <line x1="4" y1="4" x2="16" y2="16" />
                  <line x1="16" y1="4" x2="4" y2="16" />
                </>
              ) : (
                <>
                  <line x1="3" y1="5" x2="17" y2="5" />
                  <line x1="3" y1="10" x2="17" y2="10" />
                  <line x1="3" y1="15" x2="17" y2="15" />
                </>
              )}
            </svg>
          </button>
        </div>

        {/* Mobile menu */}
        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="sm:hidden overflow-hidden border-t border-white/[0.06]"
            >
              <div className="px-4 py-3 flex flex-col gap-1">
                {links.map((link) => (
                  <div key={link.href} onClick={() => setOpen(false)}>
                    <NavLink link={link} active={!link.external && pathname === link.href} />
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.nav>
  );
}
