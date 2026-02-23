# isnad Web — Design & Code Guide

This is the marketing site and dashboard for isnad — a trust verification platform for AI agents ("VirusTotal for AI agents"). The site must look like a real funded startup's product (Vercel/Linear/Stripe tier).

## Stack

- **Next.js 15** (App Router, static + dynamic routes)
- **TypeScript** strict
- **Tailwind CSS 4** (CSS-based config via `@theme inline` in globals.css)
- **Framer Motion** for all animations
- **Dark theme only** (hardcoded `className="dark"` on `<html>`)

## Design Direction: "Precision Authority"

Linear's restraint + Stripe's polish + cybersecurity terminal aesthetic. Every element should feel intentional, not decorative.

### Core Principles

1. **Restraint over ornamentation** — low opacities (0.02–0.06), thin borders, generous whitespace
2. **Typography hierarchy** — Syne for headings (authority), Inter for body (readability), JetBrains Mono for data/code (precision)
3. **Subtle depth** — glassmorphism at very low intensities, not frosted glass clichés
4. **Motion with purpose** — scroll-triggered reveals, layout animations, no gratuitous bouncing
5. **Monochrome + accent** — predominantly zinc/neutral, teal (#00d4aa) as the only strong color, indigo (#6366f1) as secondary gradient accent

## Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `--background` | `#050507` | Page background (almost black) |
| `--foreground` | `#e4e4e7` | Primary text (zinc-200) |
| `isnad-teal` | `#00d4aa` | Primary accent — CTAs, links, data highlights |
| `isnad-teal-light` | `#00e6b8` | Hover states, gradient endpoint |
| `isnad-teal-dark` | `#00b894` | Active/pressed states |
| `accent` | `#6366f1` | Secondary — gradient mixing only, never standalone |
| Card bg | `rgba(255,255,255,0.025)` | Card/surface backgrounds |
| Card border | `rgba(255,255,255,0.06)` | Borders, dividers |

### Color Rules

- **Never use teal as background fill** for large areas. Only for small elements (buttons, dots, badges)
- **Gradient text**: `bg-gradient-to-r from-isnad-teal via-isnad-teal-light to-accent bg-clip-text text-transparent`
- **Text hierarchy**: white → zinc-200 → zinc-400 → zinc-500 → zinc-600 → zinc-700
- **Interactive elements**: zinc-500 default → zinc-200 on hover
- Use `white/[0.02]`, `white/[0.03]`, `white/[0.04]` for surfaces (not `var(--card-bg)` in new code)

## Typography

| Role | Font | Class | Weights |
|------|------|-------|---------|
| Headings (h1–h3) | Syne | `font-heading` | 600–800 |
| Body text | Inter | `font-sans` (default) | 400–500 |
| Code, scores, data | JetBrains Mono | `font-mono` | 400–700 |

### Typography Patterns

```
h1: font-heading text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-bold tracking-tight
h2: font-heading text-3xl md:text-4xl font-bold tracking-tight
h3: text-lg font-semibold text-zinc-200
body: text-sm text-zinc-500 leading-relaxed
label: text-[10px] font-mono tracking-[0.2em] uppercase text-zinc-500
data: font-mono text-isnad-teal tabular-nums
```

## Component Patterns

### Cards (glassmorphic)
```
bg-white/[0.02] backdrop-blur-xl border border-white/[0.06] rounded-2xl p-6
hover: border-isnad-teal/20 bg-white/[0.04] shadow-[0_0_40px_-10px_rgba(0,212,170,0.12)]
```

### Buttons
- **Primary**: `bg-isnad-teal text-[#050507]` with hover glow `shadow-[0_0_30px_-5px_rgba(0,212,170,0.4)]`
- **Secondary**: `border border-white/[0.1] text-zinc-300` with hover `text-white bg-white/[0.05]`
- **Ghost**: `text-zinc-400` with hover `text-zinc-200 bg-white/[0.04]`

### Inputs
```
bg-white/[0.03] border border-white/[0.08] rounded-xl font-mono text-sm
focus: ring-1 ring-isnad-teal/30 border-isnad-teal/30
```

### Tables
- Header: `text-[10px] font-mono tracking-[0.15em] uppercase text-zinc-500`
- Rows: `border-b border-white/[0.04] hover:bg-white/[0.02]`
- Agent names in `font-mono text-isnad-teal`

### Badges (score-based)
- ≥80: green variant
- ≥60: yellow variant
- <60: red variant

## CSS Utilities (globals.css)

| Class | Purpose |
|-------|---------|
| `hero-mesh` | Multi-layer radial gradient background for hero sections |
| `dot-grid` | Subtle dot grid pattern overlay |
| `glow-divider` | 1px gradient line between sections (teal center, transparent edges) |

### Noise Texture
Applied via `body::before` — SVG fractalNoise at 2.5% opacity. Do not remove or modify.

## Animation Patterns

All animations use Framer Motion. Patterns:

```tsx
// Scroll-triggered section reveal
initial={{ opacity: 0, y: 30 }}
whileInView={{ opacity: 1, y: 0 }}
viewport={{ once: true }}
transition={{ duration: 0.6 }}

// Staggered children (delay based on index)
transition={{ duration: 0.5, delay: i * 0.15 }}

// Hero entrance (longer, more dramatic)
transition={{ duration: 0.8, delay: 0.15 }}

// Tab indicator
<motion.div layoutId="activeTab" />

// Animated counters
animate(0, target, { duration: 2, ease: 'easeOut' })
```

### Animation Rules
- `viewport={{ once: true }}` — always, don't re-trigger
- Delays: 0.1–0.5s range, never more
- Durations: 0.4–0.8s for sections, 1.5–2s for data visualizations
- Easing: default or `easeOut`, never `bounce`

## Layout & Spacing

- Max widths: `max-w-5xl` (content), `max-w-4xl` (cards/tables), `max-w-3xl` (text), `max-w-xl` (inputs)
- Section padding: `py-24 px-6`
- Section gap: `glow-divider` between major sections
- Card gap in grids: `gap-4`
- Navbar: floating `top-4 left-4 right-4`, `max-w-5xl mx-auto`, `h-14`

## File Structure

```
src/
├── app/           # Next.js pages
│   ├── page.tsx   # Landing page (all sections composed here)
│   ├── layout.tsx # Root layout (fonts, metadata)
│   ├── globals.css # Theme, utilities, noise texture
│   ├── check/     # Agent check page
│   ├── docs/      # Documentation page
│   └── explorer/  # Trust explorer page
├── components/
│   ├── sections/  # Page sections (hero, stats, live-check, api-tabs, etc.)
│   ├── ui/        # Reusable primitives (button, card, input, badge, navbar)
│   ├── trust-chain-hero.tsx   # SVG network visualization
│   ├── trust-score-ring.tsx   # Circular score display
│   └── radar-chart.tsx        # Spider chart for categories
└── lib/
    ├── api.ts      # API client functions
    ├── mock-data.ts # Development mock data
    └── types.ts     # TypeScript interfaces (Agent, TrustScore)
```

## Do's and Don'ts

### Do
- Use `white/[0.0X]` opacity notation for dark surfaces
- Keep SVG icons thin (strokeWidth 1.5)
- Use `font-heading` for all h1/h2 headings
- Use `font-mono` for any numerical data, scores, agent IDs
- Add `glow-divider` between major landing page sections
- Keep text subdued (zinc-500) and let teal be the accent pop
- Use `tracking-tight` on headings, `tracking-wide` or `tracking-[0.2em]` on small caps labels

### Don't
- Don't use bright white (`text-white`) for body text — use zinc-200/zinc-300
- Don't add drop shadows everywhere — reserve for hover states only
- Don't use `border-[var(--card-border)]` — use `border-white/[0.06]` directly
- Don't use the light theme — it's dark-only
- Don't import ThemeToggle on new pages (removed from nav)
- Don't use opacity higher than 0.06 for borders
- Don't use Inter for headings — always Syne (`font-heading`)
- Don't use generic Tailwind colors (blue-500, purple-500) — stick to the palette
