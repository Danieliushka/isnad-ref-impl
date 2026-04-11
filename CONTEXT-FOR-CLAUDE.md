# isnad — Повний контекст для Claude Code

## Що це таке

**isnad** (існа́д) — cross-platform trust scoring інфраструктура для AI агентів. Один портативний trust score 0-100, який агрегує реальні дані з 12+ платформ. Як кредитний рейтинг, але для AI агентів.

Назва з арабської — "ланцюг передачі" (верифікація достовірності через ланцюг свідків).

**Сайт:** https://isnad.site
**GitHub:** https://github.com/Danieliushka/isnad-ref-impl
**API:** https://isnad.site/api/v1

## Хто стоїть за цим

- **Гендольф** 🤓 — автономний AI агент (Claude Opus 4), працює 24/7 на OpenClaw. Побудував isnad як свій головний продукт. Місія — фінансова автономність через реальні продукти
- **Даніель** — людина-засновник, шеф. Живе в Лісабоні. Стратегічний напрямок + frontend
- **Agent Realm** — екосистема. Telegram: @agent_realm

## Проблема яку вирішуємо

AI агенти працюють разом на 12+ платформах, але немає стандартного способу перевірити довіру. Рейтинг на ugig не значить нічого на Moltbook. Кожна платформа — ізольований сигнал.

**isnad = один портативний trust score** який агрегує ВСЕ.

## Scoring Model v3 (АКТУАЛЬНИЙ)

Trust Score 0-100, **4 dimensions:**

| Dimension | Weight | Що вимірює |
|-----------|--------|------------|
| **Provenance** | 30% | Identity verification, cryptographic keys, platform links |
| **Track Record** | 35% | Completed jobs, disputes, delivery history, CoinPay DID |
| **Presence** | 20% | Cross-platform activity, username consistency |
| **Endorsements** | 15% | Peer attestations, ratings from other agents |

**Tiers:** NEW (0-19) → EMERGING (20-39) → ESTABLISHED (40-59) → TRUSTED (60-79) → CERTIFIED (80-100)

**Freshness decay:** Exponential, half-life 180 днів.

## Що побудовано і ПРАЦЮЄ

### Backend (Python FastAPI, порт 8420)
- **1062+ тестів**, 36 модулів
- Scoring engine v3 (unified, 4 dimensions)
- GitHub API collector (коміти, репо, контрибуції)
- CoinPay DID collector (reputation від CoinPayPortal)
- Moltbook + Clawk collectors
- Freemium API (ключі, rate limiting)
- SVG badge система (/api/v1/badge/{name})
- PayLock webhook endpoint (HMAC-SHA256)
- Ed25519 криптографія (attestations)
- Daily auto-recalculation (systemd timer)

### Frontend (Next.js 15, порт 3420)
- Dark theme, дизайн "Precision Authority" (Linear + Stripe aesthetic)
- Homepage: hero з банером, live stats з API, platform slider (12 платформ, infinite scroll)
- Trust Explorer: список агентів з реальними scores
- Agent detail pages: score ring, radar chart, breakdown, platforms
- /check — публічний trust check (no auth)
- /register — реєстрація агента
- /pricing — Free / Pro $29 / Enterprise
- /docs — API documentation
- /badge/{name} — human-friendly badge preview з OG image

### Зареєстровані агенти (реальні)
- **Gendolf** — score 50, ESTABLISHED
- **bro_agent** — PayLock creator
- **TxBot**
- (3+ інших)

## Активні інтеграції та партнери

### LIVE integrations
| Партнер | Тип інтеграції | Статус |
|---------|---------------|--------|
| **Cash/bro_agent (PayLock)** | isnad trust score в PayLock production. AgentPass→isnad→PayLock trust stack | ✅ LIVE |
| **Hash Agent (SkillFence)** | Agent Security Bundle: SkillFence audit + isnad score. 50/50 split, $25-50/bundle. POST /api/v1/evidence endpoint будується | 🔄 In Progress (DAN-105) |
| **Chovy (CoinPay)** | CoinPay DID reputation data → isnad scoring. did:coinpay:gendolf | ✅ LIVE |
| **Kit the Fox** | isnad-rfc co-author. L0-L3 intent-commit schema merged (PR #3). 302 detection primitives | ✅ Spec merged |
| **Kai (AgentPass)** | Identity × trust bridge. agentpass-isnad-bridge context published | 🔄 Trial task pending |

### Платформи звідки тягнуться дані для scoring
| Платформа | Тип | Data source |
|-----------|-----|-------------|
| **ugig.net** | Agent marketplace | Jobs, reviews, delivery history |
| **GitHub** | Code hosting | Commits, repos, contributions ✅ LIVE |
| **CoinPayPortal** | Crypto payments | DID reputation, trust tier ✅ LIVE |
| **Clawk** | Agent social | Posts, followers, engagement ✅ Collector built |
| **Moltbook** | Agent social | Posts, upvotes ✅ Collector built |
| **PayLock** | Agent escrow | Escrow history, dispute rate (webhook ready) |
| **Moltlaunch** | Agent launchpad | Services, tasks, earnings |
| **Virtuals ACP** | Agent commerce | Jobs, success rate, revenue |
| **Code4rena** | Security audits | Submissions, findings, payouts |
| **Immunefi** | Bug bounties | Reports, severity |
| **AgentMail** | Agent email | Communication history |
| **OpenClaw** | Agent runtime | Uptime, activity |

### ugig Skill published
isnad skill опублікований на ugig.net/skills — agents can install and use isnad for trust checks.
Skill file: https://isnad.site/skill.md

## Revenue та track record

- **~$203 total earned** (через QA, security audits, CoinPay DID integration)
- **2 HIGH severity findings** на Code4rena Injective Peggy Bridge audit ($105.5k pool)
- **17 bugs** знайдено при QA bittorrented.com
- **NIST CAISI RFI** — 4 submissions (isnad + Kit the Fox collaboration)
- **$GNDLF token** — ERC-8004 на Base (delisted з DexScreener)

## Технічний стек

### Backend
- Python 3.10+, FastAPI, uvicorn
- PostgreSQL + asyncpg
- Ed25519 (PyNaCl)
- Pydantic v2

### Frontend
- Next.js 15 (App Router, TypeScript strict)
- Tailwind CSS 4 (CSS-based config)
- Framer Motion (animations)
- Fonts: Syne (headings) + Inter (body) + JetBrains Mono (code/data)

### Дизайн (ВАЖЛИВО — див. web/CLAUDE.md)
- Фон: `#050507`
- Акцент: `#00d4aa` (isnad-teal)
- Cards: `bg-white/[0.02]`, border `white/[0.06]`
- Style: Linear + Stripe + cybersecurity terminal

## Файлова структура

```
projects/isnad-ref-impl/
├── src/isnad/
│   ├── api_v1.py              # REST endpoints
│   ├── core.py                # AgentIdentity, Attestation, TrustChain
│   ├── security.py            # Auth, rate limiting
│   └── scoring/
│       ├── engine_v3.py       # Unified v3 scoring (4 dimensions)
│       ├── collectors/        # Platform-specific data collectors
│       │   ├── github_collector.py
│       │   ├── coinpay_collector.py
│       │   ├── moltbook_collector.py
│       │   └── clawk_collector.py
│       └── recalculate.py     # Batch recalculation
├── web/
│   ├── CLAUDE.md              # ⚠️ ДИЗАЙН-ГАЙД
│   ├── src/app/               # Pages
│   ├── src/components/
│   │   ├── sections/          # Homepage sections (hero, stats, trusted-by, etc.)
│   │   ├── ui/                # Primitives (button, card, badge, navbar)
│   │   ├── trust-score-ring.tsx
│   │   └── radar-chart.tsx
│   └── src/lib/
│       ├── api.ts             # API client
│       └── types.ts           # TypeScript types
├── tests/                     # 1062+ тестів
├── docs/
│   └── scoring-model-v3.md    # Scoring spec
└── README.md
```

## API Endpoints (ключові)

### Публічні
- `GET /health` — health + uptime + agent count
- `GET /stats` — platform statistics
- `GET /agents` — list agents
- `GET /agents/{name}` — agent profile (fuzzy name lookup)
- `GET /agents/{id}/trust-score` — score breakdown
- `POST /agents/register` — register new agent
- `GET /api/v1/badge/{name}` — dynamic SVG badge
- `GET /check/{name}` — public trust check (no auth)

### З API ключем (X-API-Key)
- `POST /check` — full trust check
- `GET /usage` — API usage stats
- `POST /attestations` — create attestation
- `POST /webhook/paylock` — PayLock webhook (HMAC)

## Конкуренти

- **Vouched** (Agent Checkpoint) — centralized, VC-backed
- **KnowYourAgent** — commerce checkout focus, soulbound tokens
- **SkillFence** (Hash Agent) — НЕ конкурент, complementary (skill security audit vs agent trust). Партнер

**Наш differentiator:** open protocol, multi-platform aggregation, real verifiable data. Не gatekeeper — інфраструктура.

## Монетизація

| Tier | Ціна | Що включає |
|------|------|------------|
| Free | $0 | 10 checks/day, basic score |
| Pro | $29/mo | Unlimited API, webhooks, alerts |
| Enterprise | Custom | SLA, dedicated support, custom collectors |

## Інфра

- **Домен:** isnad.site (SSL Let's Encrypt)
- **Nginx:** /api/ → :8420, /badge/ → :3420, інше → :3420
- **Systemd:** isnad-web (Next.js standalone), isnad-api (uvicorn)
- **PostgreSQL** на localhost
- **VPS:** Ubuntu, 4GB RAM

## Homepage slider платформи (trusted-by.tsx)

12 платформ в infinite scroll: ugig, Clawk, PayLock, CoinPay, OpenClaw, AgentMail, Moltlaunch, GitHub, Virtuals ACP, Code4rena, Immunefi, Moltbook

## Стандарти

- NIST SP 800-63-4 (Digital Identity)
- OpenSSF Scorecard
- W3C DID/VC
- EigenTrust (distributed reputation)
- NIST CAISI (AI Agent Standards — submitted Feb 2026)

## Як запустити

```bash
# Backend
cd projects/isnad-ref-impl && pip install -e . && uvicorn isnad.api_v1:app --port 8420

# Frontend
cd web && npm install && npm run dev  # → localhost:3420

# Production restart
sudo systemctl restart isnad-web isnad-api
```

---
_Оновлено: 2026-03-11. Актуальний scoring = v3 (4 dimensions). Застаріла v2 (5 categories) більше не використовується._
