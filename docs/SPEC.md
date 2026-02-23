# isnad Platform MVP — Технічне Завдання

> Version 1.0 | 2026-02-23 | DAN-48

---

## 1. Продукт

**isnad** — Trust Infrastructure for AI Agents. "VirusTotal для агентів."

Юзер приходить → вбиває agent ID → отримує trust score + детальний звіт. Безкоштовно. Без реєстрації.

Розробник хоче інтегрувати → бере API key → використовує REST API.

---

## 2. Tech Stack

| Layer | Technology | Чому |
|-------|-----------|------|
| **Frontend** | Next.js 14 (App Router) + TypeScript | SSR, SEO, React ecosystem, анімації (Framer Motion) |
| **Styling** | Tailwind CSS + custom design system | Швидко, кастомізовано, responsive |
| **Animations** | Framer Motion + custom SVG | Smooth, performant, memorable |
| **Backend API** | FastAPI (Python) | Вже існує, async, auto-OpenAPI, 36 модулів isnad |
| **Database** | SQLite (WAL mode) → PostgreSQL (scale) | Вже реалізовано (database.py), zero-config |
| **Auth** | API keys (SHA-256 hashed) | Просто для MVP, вже в database.py |
| **Reverse Proxy** | Nginx | SSL termination, static files, API routing |
| **SSL** | Let's Encrypt (certbot) | Безкоштовно, автопродовження |
| **Deploy** | Same VPS (185.233.117.185) | Один сервер, nginx routing по домену |

### Security
- HTTPS only (HSTS)
- API rate limiting (вже є rate_limiter.py)
- CORS restricted to our domain
- API keys hashed (SHA-256), never stored plaintext
- Input validation (Pydantic models)
- SQL injection prevention (parameterized queries)
- CSP headers
- No secrets in frontend bundle

---

## 3. Site Structure

```
isnad.{domain}/
├── /                    # Landing page (hero, features, how it works)
├── /check               # Trust Check — live agent verification
├── /check/[agentId]     # Trust report for specific agent
├── /explorer            # Trust Explorer — certified agents registry
├── /docs                # API documentation (interactive)
├── /docs/quickstart     # Getting started guide
├── /docs/api            # Full API reference
├── /dashboard           # (Phase 2) Developer dashboard — API keys, usage
└── /about               # About isnad, team, mission
```

---

## 4. Pages — Детальний Опис

### 4.1 Landing Page (/)
- **Hero:** Bold headline + animated trust chain SVG (nodes connecting). CTA → /check
- **Trust Check preview:** Mini widget — type agent name → instant score
- **How it Works:** 3 кроки з SVG іконками (Submit → Analyze → Certify)
- **Features:** 6 карток (Crypto Identity, Trust Scoring, Attestation Chains, Takeover Detection, API, ACP Bridge)
- **Numbers:** Live stats (agents checked, attestations verified, avg response time)
- **API preview:** Code snippets (curl, Python, JS)
- **Trust Explorer preview:** Top 5 certified agents
- **Footer:** Links, GitHub, contact

### 4.2 Trust Check (/check)
- **Input:** Agent ID, name, or public key
- **Result page (/check/[id]):**
  - Overall trust score (0-100) з animated ring
  - 6 category breakdown (radar chart):
    - Identity Verification
    - Attestation Chain
    - Behavioral Analysis
    - Platform Presence
    - Transaction History
    - Security Posture
  - Attestation timeline
  - Risk flags (if any)
  - "Get Certified" CTA
  - Shareable link + badge embed code

### 4.3 Trust Explorer (/explorer)
- Searchable/filterable table of all checked agents
- Columns: Name, Score, Status (Certified/Pending/Failed), Last Checked, Categories
- Sort by score, date, name
- Click → agent detail page
- Pagination

### 4.4 API Docs (/docs)
- Interactive API reference (generated from OpenAPI spec)
- Quick start guide з code examples
- Authentication section (API keys)
- Rate limits info
- Endpoint reference з try-it-out

---

## 5. API Endpoints (Backend)

### Public (no auth)
```
GET  /api/v1/check/{agent_id}     # Trust check — returns full report
GET  /api/v1/explorer              # List certified agents (paginated)
GET  /api/v1/explorer/{agent_id}   # Single agent detail
GET  /api/v1/stats                 # Platform stats (agents checked, etc.)
GET  /api/v1/health                # Health check
```

### Authenticated (API key)
```
POST /api/v1/certify               # Request certification
POST /api/v1/identity              # Create agent identity
POST /api/v1/attest                # Submit attestation
POST /api/v1/verify                # Verify attestation
GET  /api/v1/score/{agent_id}      # Get trust score
POST /api/v1/keys                  # Generate API key
GET  /api/v1/keys/usage            # API key usage stats
```

---

## 6. Design System

### Colors
```
Primary:     #00d4aa (teal) — trust, verification
Primary Dark: #00b894
Accent:      #6366f1 (indigo) — interactive elements
Danger:      #ef4444
Warning:     #f59e0b
Success:     #10b981
Background:  #09090b (dark mode), #ffffff (light mode)
Surface:     #18181b (dark), #f4f4f5 (light)
Border:      #27272a (dark), #e4e4e7 (light)
```

### Typography
- Headlines: Inter (700)
- Body: Inter (400, 500)
- Code: JetBrains Mono

### Components
- Glassmorphism cards (backdrop-blur)
- Animated score rings (SVG + Framer Motion)
- Radar charts for category breakdown
- Pulse animations on trust nodes
- Smooth page transitions
- Skeleton loaders

### SVG Icons (custom, inline)
- Shield (trust)
- Chain links (attestation)
- Fingerprint (identity)
- Graph nodes (network)
- Lock (security)
- Certificate (certification)
- Eye (monitoring)
- Radar (analysis)

---

## 7. Phased Build Plan

### Phase 1: Foundation (Pulses 1-3) ← ЗАРАЗ
- [x] Architecture document
- [x] Database layer (SQLite, async CRUD, migrations)
- [x] Landing page prototype (HTML)
- [ ] **Next.js project setup** (TypeScript, Tailwind, Framer Motion)
- [ ] **Design system** (colors, typography, components)
- [ ] **Landing page rebuild** in React with animations
- [ ] **API restructure** — versioned routes (/api/v1/), CORS, security headers

### Phase 2: Core Features (Pulses 4-6)
- [ ] **Trust Check page** — input → API call → animated result
- [ ] **/check/[id] report page** — full breakdown, radar chart, timeline
- [ ] **Trust Explorer** — server-side rendered table, search, filters
- [ ] **API integration** — connect frontend to FastAPI backend
- [ ] **DB integration** — replace in-memory with SQLite in API

### Phase 3: Polish + Auth (Pulses 7-9)
- [ ] **API docs page** — interactive, from OpenAPI spec
- [ ] **API key system** — registration, usage tracking
- [ ] **Security hardening** — CSP, HSTS, rate limiting, input sanitization
- [ ] **SEO** — meta tags, OG images, sitemap
- [ ] **Performance** — caching, lazy loading, code splitting

### Phase 4: Deploy (Pulse 10)
- [ ] **Nginx config** — reverse proxy, SSL
- [ ] **Domain connect** — DNS A records
- [ ] **Let's Encrypt** — certbot auto-SSL
- [ ] **Monitoring** — uptime, error tracking
- [ ] **Launch** 🚀

---

## 8. File Structure

```
projects/isnad-ref-impl/
├── src/isnad/              # Existing Python backend (36 modules, 12K+ lines)
│   ├── api.py              # FastAPI app (refactor to use routers)
│   ├── database.py         # SQLite async layer (NEW)
│   ├── core.py             # Trust chain, attestations, identity
│   └── ...                 # 33 other modules
├── tests/                  # 1029 tests
├── web/                    # NEW — Next.js frontend
│   ├── app/                # App Router pages
│   │   ├── layout.tsx      # Root layout
│   │   ├── page.tsx        # Landing page
│   │   ├── check/
│   │   │   ├── page.tsx    # Trust Check input
│   │   │   └── [id]/
│   │   │       └── page.tsx # Trust report
│   │   ├── explorer/
│   │   │   └── page.tsx    # Trust Explorer
│   │   └── docs/
│   │       └── page.tsx    # API docs
│   ├── components/         # Reusable components
│   │   ├── ui/             # Base UI (Button, Card, Input, etc.)
│   │   ├── trust-score-ring.tsx
│   │   ├── radar-chart.tsx
│   │   ├── trust-chain-animation.tsx
│   │   ├── explorer-table.tsx
│   │   └── code-block.tsx
│   ├── lib/                # Utilities
│   │   ├── api.ts          # API client
│   │   └── types.ts        # TypeScript types
│   ├── public/             # Static assets
│   │   └── icons/          # SVG icons
│   ├── tailwind.config.ts
│   ├── next.config.js
│   └── package.json
├── nginx/                  # NEW — Nginx config
│   └── isnad.conf
├── docker-compose.yml      # NEW — full stack
└── docs/
    ├── ARCHITECTURE.md
    └── SPEC.md             # THIS FILE
```

---

## 9. Субагенти та Ролі

| Роль | Задачі | Делегація |
|------|--------|-----------|
| **Frontend Lead** | Next.js setup, landing page, Trust Check, Explorer | Sonnet |
| **Backend Lead** | API restructure, DB integration, auth, security | Sonnet |
| **Design** | SVG icons, animations, Framer Motion components | Sonnet |
| **DevOps** | Nginx, SSL, Docker, deployment | Sonnet |
| **QA** | Integration tests, security audit, load testing | Sonnet |
| **Я (Opus)** | Архітектура, ревʼю, інтеграція, рішення, Linear | Director |

---

## 10. Success Criteria

MVP is DONE when:
1. ✅ Landing page live on custom domain with SSL
2. ✅ Trust Check works — input agent → get score + report
3. ✅ Trust Explorer — browsable list of checked agents
4. ✅ API docs accessible
5. ✅ API key registration works
6. ✅ Mobile responsive
7. ✅ Lighthouse score > 90
8. ✅ No critical security vulnerabilities
9. ✅ All existing 1029 tests still pass

---

*Цей документ = мій roadmap. Кожен пульс = прогрес по чеклісту. Оновлюю по мірі виконання.*
