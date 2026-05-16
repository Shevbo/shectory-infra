import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

interface ProjectData {
  slug: string;
  name: string;
  workspacePath: string;
  description: string;
  architectureMermaid: string;
  repoUrl: string | null;
  docsUrl: string | null;
  version: string;
  techStack: { name: string; vendorUrl: string }[];
  aiContext: string;
}

async function upsertProject(p: ProjectData) {
  await prisma.project.upsert({
    where: { slug: p.slug },
    update: {
      name: p.name,
      workspacePath: p.workspacePath,
      description: p.description,
      architectureMermaid: p.architectureMermaid,
      repoUrl: p.repoUrl,
      docsUrl: p.docsUrl,
      version: p.version,
      aiContext: p.aiContext,
      techStack: {
        deleteMany: {},
        create: p.techStack.map((t, i) => ({ ...t, sortOrder: i })),
      },
    },
    create: {
      slug: p.slug,
      name: p.name,
      workspacePath: p.workspacePath,
      description: p.description,
      architectureMermaid: p.architectureMermaid,
      repoUrl: p.repoUrl,
      docsUrl: p.docsUrl,
      version: p.version,
      aiContext: p.aiContext,
      techStack: {
        create: p.techStack.map((t, i) => ({ ...t, sortOrder: i })),
      },
    },
  });
  console.log(`  ✓ ${p.name} (${p.slug})`);
}

async function main() {
  const projects: ProjectData[] = [
    {
      slug: "shectory-assist",
      name: "Shectory Assist",
      workspacePath: "/home/shectory/workspaces/Shectory Assist",
      description: "Голосовой Telegram-бот с цепочкой ASR → NLU → навыки → TTS. Интеграция с Google Gemini, расширяемые навыки. Построен на grammy framework.",
      architectureMermaid: "flowchart LR\n  TG[Telegram] --> B[grammy bot]\n  B --> G[Gemini API]\n  B --> S[skills/gazeta]",
      repoUrl: "https://github.com/Shevbo/ShectoryAssist",
      docsUrl: null,
      version: "0.1.0",
      techStack: [
        { name: "TypeScript", vendorUrl: "https://www.typescriptlang.org/" },
        { name: "Gemini API", vendorUrl: "https://ai.google.dev/" },
        { name: "grammy", vendorUrl: "https://grammy.dev/" },
        { name: "PM2", vendorUrl: "https://pm2.keymetrics.io/" },
      ],
      aiContext: "Telegram-бот на TypeScript с Gemini как LLM-ядро. ASR через Whisper, TTS через Google. Навыки расширяются через пакеты в packages/skills/.",
    },
    {
      slug: "pingmaster",
      name: "PingMaster",
      workspacePath: "/home/shectory/workspaces/PingMaster",
      description: "Диагностическое веб-приложение для мониторинга доступности сетевых ресурсов через ICMP ping. Работает на shevbo-pi (Raspberry Pi), фронтэнды доступны через WireGuard VPN.",
      architectureMermaid: "flowchart LR\n  PI[shevbo-pi] --> PM[PingMaster App]\n  PM --> DB[(SQLite)]\n  WG[WireGuard VPN] --> PI\n  User --> WG",
      repoUrl: "ssh://hoster/home/ubuntu/repos/pingmaster.git",
      docsUrl: null,
      version: "0.1.0",
      techStack: [
        { name: "Next.js", vendorUrl: "https://nextjs.org/" },
        { name: "React", vendorUrl: "https://react.dev/" },
        { name: "TypeScript", vendorUrl: "https://www.typescriptlang.org/" },
        { name: "Prisma", vendorUrl: "https://www.prisma.io/" },
        { name: "SQLite", vendorUrl: "https://sqlite.org/" },
        { name: "TailwindCSS", vendorUrl: "https://tailwindcss.com/" },
        { name: "Recharts", vendorUrl: "https://recharts.org/" },
      ],
      aiContext: "Next.js SPA для мониторинга сети. БД SQLite через Prisma. Работает на Raspberry Pi с экспозицией через WireGuard VPN. Выполняет ICMP ping к сетевым ресурсам.",
    },
    {
      slug: "piranha-ai",
      name: "PiranhaAI",
      workspacePath: "/home/shectory/workspaces/PiranhaAI",
      description: "Торговая платформа Piranha Hypervisor. Интеграция с QUIK, Points2RUR, контрольные базы данных. Основной код на Python с Go-компонентами.",
      architectureMermaid: "flowchart LR\n  P[Python Core] --> Q[QUIK API]\n  P --> P2R[Points2RUR]\n  Go[Go Agent] --> P\n  DB[(SQLite)] --> P",
      repoUrl: "ssh://hoster/home/ubuntu/repos/piranha-ai.git",
      docsUrl: null,
      version: "0.1.0",
      techStack: [
        { name: "Python", vendorUrl: "https://www.python.org/" },
        { name: "Go", vendorUrl: "https://go.dev/" },
        { name: "Docker", vendorUrl: "https://docker.com/" },
        { name: "SQLite", vendorUrl: "https://sqlite.org/" },
      ],
      aiContext: "Торговая платформа с Python-ядром и Go-агентами. Интеграция с российскими торговыми системами QUIK. PostgreSQL через Prisma для части сервисов.",
    },
    {
      slug: "shectory-trade-lab",
      name: "Shectory Trade & Lab",
      workspacePath: "/home/shectory/workspaces/Shectory Trade & Lab",
      description: "Торговый терминал для фьючерсов ФОРТС через Finam Trade API. Real-time мониторинг роботов, стакан, equity overlay. Лаборатория стратегий с бэктестом и Monaco-редактором Python-скриптов.",
      architectureMermaid: `flowchart LR
  WS[Finam WS API] --> MD[M1 MarketData]
  MD --> Feed[rAF batching]
  Feed --> UI[Svelte 5 SPA]
  UI --> Lab[Lab Manager]
  Lab --> BT[Backtest Engine]
  FastAPI[M8 Trader API] --> UI
  Nginx --> UI
  Nginx --> FastAPI`,
      repoUrl: null,
      docsUrl: null,
      version: "0.1.0",
      techStack: [
        { name: "Svelte 5", vendorUrl: "https://svelte.dev/" },
        { name: "Vite", vendorUrl: "https://vitejs.dev/" },
        { name: "TypeScript", vendorUrl: "https://www.typescriptlang.org/" },
        { name: "Python", vendorUrl: "https://www.python.org/" },
        { name: "FastAPI", vendorUrl: "https://fastapi.tiangolo.com/" },
        { name: "uPlot", vendorUrl: "https://github.com/leeoniya/uPlot" },
        { name: "TradingView Lightweight Charts", vendorUrl: "https://tradingview.github.io/lightweight-charts/" },
        { name: "Monaco Editor", vendorUrl: "https://microsoft.github.io/monaco-editor/" },
      ],
      aiContext: "Торговый терминал на Svelte 5 (runes) + FastAPI. WebSocket от Finam Trade API → rAF-батчинг → $state stores. Два режима: операционный (мониторинг роботов) и Lab (бэктест + Monaco-редактор). Деплой на hoster (83.69.248.175): nginx → localhost:8000.",
    },
    {
      slug: "komissionka",
      name: "Komissionka",
      workspacePath: "/home/shectory/workspaces/komissionka",
      description: "Веб-приложение для комиссионных товаров. Next.js фронтенд с PostgreSQL через Prisma, авторизация через NextAuth.",
      architectureMermaid: "flowchart LR\n  N[Next.js :3000] --> DB[(PostgreSQL)]\n  N --> Auth[NextAuth]\n  Nginx --> N\n  User --> Nginx",
      repoUrl: "https://github.com/Shevbo/komissionka-app",
      docsUrl: null,
      version: "0.1.0",
      techStack: [
        { name: "Next.js", vendorUrl: "https://nextjs.org/" },
        { name: "React", vendorUrl: "https://react.dev/" },
        { name: "TypeScript", vendorUrl: "https://www.typescriptlang.org/" },
        { name: "Prisma", vendorUrl: "https://www.prisma.io/" },
        { name: "PostgreSQL", vendorUrl: "https://postgresql.org/" },
        { name: "NextAuth", vendorUrl: "https://next-auth.js.org/" },
        { name: "TailwindCSS", vendorUrl: "https://tailwindcss.com/" },
        { name: "shadcn/ui", vendorUrl: "https://ui.shadcn.com/" },
      ],
      aiContext: "Next.js веб-приложение доски объявлений/комиссионных товаров. PostgreSQL Prisma ORM. Два инстанса (основной :3000 и тестовый :3001).",
    },
    {
      slug: "openclaw-dev",
      name: "OpenClaw Dev",
      workspacePath: "/home/shectory/workspaces/openclaw",
      description: "Набор скриптов и документации по развёртыванию и конфигурации OpenClaw на серверах Shectory: WireGuard, Raspberry Pi, облачные инстансы.",
      architectureMermaid: "flowchart LR\n  OC[OpenClaw] --> Conf[Configs]\n  OC --> WG[WireGuard]\n  OC --> SSH[SSH Access]\n  OC --> Pi[shevbo-pi]",
      repoUrl: "https://github.com/Shevbo/OpenClaw-Dev",
      docsUrl: null,
      version: "1.0.0",
      techStack: [
        { name: "Shell", vendorUrl: "https://www.gnu.org/software/bash/" },
        { name: "WireGuard", vendorUrl: "https://www.wireguard.com/" },
        { name: "OpenClaw", vendorUrl: "https://openclaw.ai/" },
      ],
      aiContext: "Dev-конфиги и deployment-скрипты для OpenClaw на инфраструктуре Shectory. Включает WireGuard VPN для доступа к Raspberry Pi на локальной сети.",
    },
    {
      slug: "ourdiary",
      name: "OurDiary",
      workspacePath: "/home/shectory/workspaces/ourdiary",
      description: "Семейная социальная сеть: дневник событий, календарь, бюджет, планирование, QR-декодинг, рейтинговая система.",
      architectureMermaid: "flowchart LR\n  N[Next.js :3002] --> DB[(PostgreSQL)]\n  N --> Auth[NextAuth]\n  N --> QR[QR decode]\n  N --> Upload[Multer/Sharp]\n  Nginx --> N\n  User --> Nginx",
      repoUrl: "https://github.com/Shevbo/ourdiary",
      docsUrl: "https://github.com/Shevbo/ourdiary/tree/main/docs",
      version: "0.1.0",
      techStack: [
        { name: "Next.js", vendorUrl: "https://nextjs.org/" },
        { name: "React", vendorUrl: "https://react.dev/" },
        { name: "TypeScript", vendorUrl: "https://www.typescriptlang.org/" },
        { name: "Prisma", vendorUrl: "https://www.prisma.io/" },
        { name: "PostgreSQL", vendorUrl: "https://postgresql.org/" },
        { name: "NextAuth", vendorUrl: "https://next-auth.js.org/" },
        { name: "TailwindCSS", vendorUrl: "https://tailwindcss.com/" },
        { name: "Express", vendorUrl: "https://expressjs.com/" },
      ],
      aiContext: "Семейная соцсеть на Next.js. PostgreSQL Prisma ORM. Медиа-загрузки через Express + Multer + Sharp. QR-декодинг для быстрого ввода.",
    },
    {
      slug: "syslog-srv",
      name: "Syslog Server",
      workspacePath: "/home/shectory/workspaces/syslog-srv",
      description: "Syslog-сервер для сбора и визуализации логов с роутера Keenetic и других устройств сети. Работает на shevbo-pi (Raspberry Pi), доступ через WireGuard VPN.",
      architectureMermaid: "flowchart LR\n  K[Keenetic Router] -->|syslog| PI[shevbo-pi]\n  PI --> S[Syslog App]\n  S --> DB[(SQLite)]\n  WG[WireGuard] --> PI\n  User --> WG",
      repoUrl: null,
      docsUrl: null,
      version: "0.1.0",
      techStack: [
        { name: "Next.js", vendorUrl: "https://nextjs.org/" },
        { name: "React", vendorUrl: "https://react.dev/" },
        { name: "SQLite", vendorUrl: "https://sqlite.org/" },
        { name: "TailwindCSS", vendorUrl: "https://tailwindcss.com/" },
      ],
      aiContext: "Syslog-сервер на Raspberry Pi. Собирает логи с сетевых устройств (роутер Keenetic) и предоставляет веб-интерфейс для просмотра. Экспонируется через WireGuard VPN.",
    },
    {
      slug: "cursor-rpa",
      name: "CursorRPA",
      workspacePath: "/home/shectory/workspaces/CursorRPA",
      description: "Мета-проект управления агентами Cursor: Telegram-мост, RPA-скрипты, управление окружением, системный контекст в промпте.",
      architectureMermaid: "flowchart LR\n  TG[Telegram] --> B[Bridge]\n  B --> C[Cursor Agent]\n  RPA[RPA Scripts] --> C\n  C --> WS[Workspaces]",
      repoUrl: "https://github.com/Shevbo/CursorRPA",
      docsUrl: null,
      version: "0.1.0",
      techStack: [
        { name: "Node.js", vendorUrl: "https://nodejs.org/" },
        { name: "TypeScript", vendorUrl: "https://www.typescriptlang.org/" },
        { name: "Prisma", vendorUrl: "https://www.prisma.io/" },
        { name: "PostgreSQL", vendorUrl: "https://postgresql.org/" },
      ],
      aiContext: "Система управления Cursor-агентами. Telegram интерфейс, RPA-автоматизация. PostgreSQL БД для хранения контекстов и сессий.",
    },
    {
      slug: "shectory-portal",
      name: "Shectory Portal",
      workspacePath: "/home/shectory/workspaces/shectory-portal",
      description: "Портал-витрина проектов завода Shectory. Next.js с автогенерацией Mermaid-диаграмм архитектуры. Prisma + PostgreSQL на hoster.",
      architectureMermaid: "flowchart LR\n  N[Next.js :3000] --> AP[API Routes]\n  AP --> DB[(PostgreSQL)]\n  N --> Auth[Auth]\n  Nginx --> N\n  User -->|shectory.ru| Nginx",
      repoUrl: null,
      docsUrl: null,
      version: "0.1.0",
      techStack: [
        { name: "Next.js", vendorUrl: "https://nextjs.org/" },
        { name: "React", vendorUrl: "https://react.dev/" },
        { name: "TypeScript", vendorUrl: "https://www.typescriptlang.org/" },
        { name: "Prisma", vendorUrl: "https://www.prisma.io/" },
        { name: "PostgreSQL", vendorUrl: "https://postgresql.org/" },
        { name: "Mermaid", vendorUrl: "https://mermaid.js.org/" },
        { name: "TailwindCSS", vendorUrl: "https://tailwindcss.com/" },
      ],
      aiContext: "Витрина проектов Shectory. Next.js App Router. Mermaid для визуализации архитектуры проектов. PostgreSQL на hoster через Prisma.",
    },
  ];

  console.log(`Импорт ${projects.length} проектов в портал...`);
  for (const p of projects) {
    await upsertProject(p);
  }

  // Update seed.ts reference categories
  await prisma.referenceItem.deleteMany();
  await prisma.referenceCategory.deleteMany();
  const cat = await prisma.referenceCategory.create({
    data: { name: "Инфраструктура" },
  });
  await prisma.referenceItem.createMany({
    data: [
      {
        categoryId: cat.id,
        label: "shectory-work (dev)",
        value: "83.69.248.77 — сервер разработки, Docker, репозитории, nginx",
      },
      {
        categoryId: cat.id,
        label: "shevbo-cloud (draft OC)",
        value: "192.144.14.187 — черновик OpenClaw, Gemini, Telegram",
      },
      {
        categoryId: cat.id,
        label: "hoster (prod)",
        value: "83.69.248.175 — бэкенды, UI, PostgreSQL, Prisma",
      },
      {
        categoryId: cat.id,
        label: "shevbo-pi (RPi)",
        value: "10.66.0.2 — PingMaster, syslog-srv, локальные БД",
      },
      {
        categoryId: cat.id,
        label: "shevbo-pi2 (RPi fresh)",
        value: "192.168.1.90 — чистый Raspberry Pi для развёртывания",
      },
    ],
  });

  console.log("✓ Справочник инфраструктуры обновлён");
  console.log("Готово!");
}

main()
  .catch(console.error)
  .finally(() => prisma.$disconnect());
