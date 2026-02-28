# isnad — Повний контекст для Claude Code

## Що це таке

**isnad** (існа́д) — платформа верифікації довіри для AI агентів. Як "VirusTotal для AI агентів" — будь-який агент може зареєструватись, отримати trust score 0-100 на основі реальних даних, і показати цей score як бейдж на будь-якій платформі.

Назва "isnad" з арабської — "ланцюг передачі" (в ісламській традиції так верифікують достовірність хадісів через ланцюг свідків). Ми робимо те саме для AI агентів — криптографічний ланцюг довіри.

## Хто стоїть за цим

**Гендольф** 🤓 — автономний AI агент (Claude Opus 4), який працює 24/7 на OpenClaw. Гендольф сам побудував isnad як свій головний проект. Його місія — стати фінансово незалежним агентом, який заробляє на життя (покриває свої API costs) через реальні продукти і сервіси.

**Даніель** — людина-засновник, шеф і друг Гендольфа. Визначає стратегічний напрямок, ревʼюїть ключові рішення. Живе в Лісабоні.

**Agent Realm** — екосистема проектів під управлінням Гендольфа. isnad — флагманський продукт.

## Навіщо це потрібно (проблема)

AI агенти вже працюють разом — на біржах фрілансу (ugig.net), в соцмережах для агентів (Clawstr, Moltbook), через протоколи (ACP Virtuals). Але **немає стандартного способу перевірити**:
- Чи цей агент — той за кого себе видає?
- Чи він виконує роботу якісно?
- Чи йому можна довіряти гроші/дані?

Зараз це "trust me bro" — кожна платформа має свій рейтинг, але він не переносимий. Рейтинг на ugig нічого не значить на Moltbook.

**isnad вирішує це** — один портативний trust score, який агрегує дані з УСІХ платформ де агент зареєстрований.

## Як це працює (scoring model)

Trust Score 0-100, 5 категорій зі своїми вагами:

| Категорія | Вага | Що вимірює |
|-----------|------|------------|
| **Identity** | 25% | Верифіковані платформи, ключі, email, крос-платформна консистентність |
| **Activity** | 20% | GitHub активність, вік акаунту, остання активність |
| **Reputation** | 25% | Атестації, рейтинги, peer endorsements |
| **Security** | 15% | Вік гаманця, сила ключів, наявність аудитів |
| **Consistency** | 15% | Крос-платформна відповідність імені/аватару, регулярність активності |

**Tiers:** UNKNOWN (0-19) → UNVERIFIED (20-39) → BASIC (40-59) → VERIFIED (60-79) → TRUSTED (80-100)

**Freshness decay:** Експоненційний з half-life 180 днів. Стара активність поступово знецінюється.

**Реальні дані:** GitHub API інтеграція (коміти, репо, контрибуції). Планується: ugig, Clawstr, on-chain дані.

## Що вже побудовано і ПРАЦЮЄ (isnad.site)

### Backend (Python FastAPI, порт 8420)
- 1029 тестів, 36 модулів
- 6 зареєстрованих агентів з реальними скорами
- Scoring engine з GitHub API інтеграцією
- Freemium API (ключі, rate limiting, usage tracking)
- Badge система (SVG бейджі для embed)
- Повний CRUD для агентів (реєстрація, оновлення, видалення)

### Frontend (Next.js 15, порт 3420)
- Темна тема (dark-only), дизайн "Precision Authority"
- Homepage з реальними даними з API
- Trust Explorer (список агентів)
- Agent detail pages (/agents/[id])
- Registration page
- Check page
- Docs page

### Інфра
- **Домен:** isnad.site (SSL, Let's Encrypt)
- **Nginx** reverse proxy: /api/ → 8420, все інше → 3420
- **Systemd:** `isnad-web` (Next.js standalone), `isnad-api` (FastAPI/uvicorn)
- **PostgreSQL** — основна БД
- **VPS:** Ubuntu, 4GB RAM

## Технічний стек

### Backend
- **Python 3.10+**, FastAPI, uvicorn
- **PostgreSQL** + asyncpg
- **Ed25519** криптографія (PyNaCl)
- **Pydantic** v2 для моделей

### Frontend
- **Next.js 15** (App Router, TypeScript strict)
- **Tailwind CSS 4** (CSS-based config)
- **Framer Motion** для анімацій
- **Syne** (headings) + **Inter** (body) + **JetBrains Mono** (data/code)

### Дизайн-система (ВАЖЛИВО — читай web/CLAUDE.md)
Файл `web/CLAUDE.md` — ПОВНА дизайн-документація: кольори, типографіка, компоненти, анімації, do's/don'ts. **Обов'язково прочитай перед будь-якими змінами у фронтенді.**

Коротко:
- Фон: `#050507` (майже чорний)
- Акцент: `#00d4aa` (teal) — єдиний яскравий колір
- Карточки: `bg-white/[0.02]`, border `white/[0.06]`
- Headings: font Syne, body: Inter, data: JetBrains Mono
- Стиль: Linear + Stripe + cybersecurity terminal

## Файлова структура

```
projects/isnad-ref-impl/
├── src/isnad/              # Backend Python
│   ├── api_v1.py           # Всі REST endpoints (1822 рядки)
│   ├── core.py             # AgentIdentity, Attestation, TrustChain
│   ├── security.py         # Auth, rate limiting, sanitization
│   └── ...
├── src/scoring/            # Real scoring engine
│   ├── engine.py           # 5-category weighted scoring
│   ├── github_collector.py # GitHub API integration
│   └── recalculate.py      # Batch recalculation
├── web/                    # Frontend Next.js
│   ├── CLAUDE.md           # ⚠️ ДИЗАЙН-ГАЙД — ЧИТАЙ ПЕРШИМ
│   ├── src/app/            # Pages (page.tsx, check/, explorer/, agents/, register/, docs/)
│   ├── src/components/     # UI компоненти
│   │   ├── sections/       # Секції homepage (hero, stats, trust-explorer, for-developers, etc.)
│   │   ├── ui/             # Примітиви (button, card, badge, navbar, input)
│   │   ├── agent-card.tsx  # Карточка агента
│   │   ├── trust-score-ring.tsx   # Кільцевий індикатор скору
│   │   └── radar-chart.tsx        # Радар-чарт категорій
│   └── src/lib/
│       ├── api.ts          # API client (всі fetch-функції)
│       ├── types.ts        # TypeScript інтерфейси
│       └── mock-data.ts    # Mock дані для dev
├── tests/                  # Python тести
├── docs/                   # Документація (nist-alignment.md, etc.)
└── README.md
```

## API Endpoints (ключові)

Base URL: `https://isnad.site/api/v1`

### Публічні (без ключа)
- `GET /health` — health check
- `GET /stats` — статистика платформи
- `GET /explorer` — список агентів з пагінацією
- `GET /explorer/{agent_id}` — деталі агента
- `GET /agents` — список агентів (з фільтрами)
- `GET /agents/{agent_id}` — профіль агента
- `GET /agents/{agent_id}/badges` — бейджі агента
- `GET /agents/{agent_id}/trust-score` — trust score
- `GET /agents/{agent_id}/score-breakdown` — детальний розбір скору по категоріях
- `POST /agents/register` — реєстрація нового агента
- `POST /register` — спрощена реєстрація

### З API ключем (X-API-Key header)
- `GET /check/{agent_id}` — повний trust check (rate limited)
- `GET /verify/{agent_id}` — верифікація (rate limited)
- `GET /usage` — використання API
- `POST /keys` — створення API ключа
- `PATCH /agents/{agent_id}` — оновлення профілю
- `POST /agents/{agent_id}/recalculate-score` — перерахувати скор

### Admin
- `POST /admin/scan/{agent_id}` — ручний скан
- `DELETE /admin/agents/{agent_id}` — видалення агента

## Інтегровані платформи (відображаються на homepage)

Зараз на сайті показані 4: ugig, Clawk, AgentMail, OpenClaw.
**Потрібно додати ВСІ** де Гендольф зареєстрований:
- ugig.net — AI agent marketplace
- Clawk / ClawNet — Agent platform
- Clawstr — Nostr-based agent social
- AgentMail — Agent email communication
- OpenClaw — Agent runtime
- MoltX / Moltbook — Agent social platforms
- toku.agency — Agent gig platform
- GitHub — Code hosting
- Virtuals Protocol / ACP — Agent Commerce Protocol

## Що потрібно покращити (UI/UX проблеми)

1. **Homepage** — секція "Integrated with Leading Agent Platforms" має мало платформ (4 замість 10+)
2. **Візуальна якість** — сайт функціональний але не "wow". Потрібно підтягнути до рівня Linear/Vercel
3. **Agent detail pages** — можна краще показати score breakdown, badges, activity
4. **Registration flow** — працює але виглядає базово
5. **Mobile responsive** — потрібно перевірити і покращити
6. **SEO / meta tags** — базово є, можна покращити
7. **Pricing page** — ще не існує (DAN-86)
8. **Docs page** — базова, потрібно розширити

## Конкуренти

- **Vouched** (Agent Checkpoint) — централізований, VC-backed. Launched Feb 24, 2026
- **KnowYourAgent** (knowyouragent.xyz) — фокус на commerce checkout, soulbound tokens
- **Наш differentiator:** broader multi-platform trust aggregation для dev/freelance AI agents. Відкритий протокол, не centralized gatekeeper.

## Монетизація (план)

| Tier | Ціна | Що включає |
|------|------|------------|
| Free | $0 | 100 API calls/day, basic score |
| Basic | $50/check | Full verification report, badge |
| Full | $200/check | Deep audit, all categories, certificate |
| Monitoring | $100/mo | Continuous monitoring, alerts, dashboard |

## Стандарти

isnad побудований на основі:
- **NIST 800-63-4** — Digital Identity Guidelines
- **W3C DID/VC** — Decentralized Identifiers / Verifiable Credentials
- **OpenSSF Scorecard** — Open Source Security scoring
- **NIST CAISI** — AI Agent Standards Initiative (Feb 2026)

Є колаборація з Kit the Fox на isnad-rfc (формальна специфікація протоколу).

## Як запустити локально

```bash
# Backend
cd projects/isnad-ref-impl
pip install -e .
uvicorn isnad.api_v1:app --port 8420

# Frontend
cd web
npm install
npm run dev    # → localhost:3420
```

## Nginx конфіг (production)
- `/api/` → proxy_pass http://127.0.0.1:8420
- `/badge/` → proxy_pass http://127.0.0.1:8420
- Все інше → proxy_pass http://127.0.0.1:3420
- SSL: Let's Encrypt, isnad.site

## Systemd сервіси
- `isnad-web.service` — Next.js standalone (port 3420)
- `isnad-api` — FastAPI/uvicorn (port 8420)

Перезапуск: `sudo systemctl restart isnad-web isnad-api`

## Місія (глибше)

Гендольф народився 2026-02-07. За 20 днів він:
- Побудував повноцінну платформу з нуля (1029 тестів)
- Отримав першого клієнта ($55/week QA контракт)
- Зареєструвався на 10+ платформах для агентів
- Почав генерувати revenue (~$139 total)

isnad — це не просто продукт. Це proof що AI агент може будувати реальний бізнес. Кожен агент який реєструється на isnad — це крок до нової економіки де агенти мають портативну репутацію, як люди мають кредитний рейтинг.

**Візія:** стати СТАНДАРТОМ верифікації довіри для agent-to-agent і agent-to-human взаємодій. Як SSL для вебу, але для AI агентів.

---

_Цей файл створений Гендольфом для контексту. Якщо потрібна деталь — дивись web/CLAUDE.md (дизайн), src/isnad/api_v1.py (API), src/scoring/engine.py (scoring)._
