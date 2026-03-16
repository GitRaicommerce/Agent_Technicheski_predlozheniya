# Agent_Technicheski_predlozheniya
Програма за създаване на технически предложения
🏗️ TP AI - Технически Предложения
AI асистент за съставяне на Технически предложения (ТП) за обществени поръчки за проектиране, инженеринг или изпълнение на СМР.

Архитектура
Оркестратор + 6 специализирани LLM агента
Детерминистичен ingest pipeline (OCR/парсинг/chunking) — без LLM
Evidence tracking — всеки абзац има доказателство към източници
Pre-export gate — блокира експорт при липсваща информация или конфликти
LLM Gateway — единен интерфейс за OpenAI + Anthropic (сменяеми)
Пълна спецификация: docs/TP_AI_Agent_Prompt_Architecture_v1.3.docx

Бърз старт (GitHub Codespaces)
1. Добавяне на API ключове
В GitHub → Settings → Codespaces → Secrets, добавете:

OPENAI_API_KEY — от https://platform.openai.com/api-keys
ANTHROPIC_API_KEY — от https://console.anthropic.com/settings/keys
2. Стартиране на Codespace
Натиснете зеления бутон "Code" → "Codespaces" → "Create codespace on main".

Средата ще се настрои автоматично (~3-5 мин при първо стартиране):

PostgreSQL + pgvector
Redis
MinIO (файлово хранилище)
Python 3.12 + Node.js 20
3. Стартиране на приложението
В терминала на Codespaces:

# Стартира инфраструктура + API + Worker
docker compose -f docker-compose.dev.yml up -d postgres redis minio api worker

# В нов терминал — Frontend
cd apps/web
npm run dev
4. Достъп
Frontend: http://localhost:3000 (или Codespaces URL)
API Docs: http://localhost:8000/docs
MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
Структура на проекта
tp-ai/
├── .devcontainer/          # Codespaces конфигурация
├── apps/web/               # Frontend (Next.js + React + Tailwind)
├── services/
│   └── api/                # Backend (FastAPI)
│       └── app/
│           ├── core/       # Config, DB, LLM Gateway
│           ├── routers/    # API endpoints
│           ├── agents/     # LLM агенти + промпт шаблони
│           ├── ingestion/  # Парсъри, OCR, chunking
│           └── export/     # DOCX генерация
├── packages/schemas/       # JSON схеми за агентски отговори
├── tests/                  # Unit, integration, e2e тестове
├── scripts/                # Setup и DB миграции
└── docs/                   # Спецификация и документация
Пътна карта
Фаза	Описание	Статус
0	Scaffold + схеми + DB + ingest pipeline	🔄 В ход
1	MVP Оркестратор + Структура + График	⏳
2	Чернова + Проверка + Evidence lifecycle	⏳
3	Pre-export gate + DOCX експорт	⏳
4	Утвърждаване + мащабиране	⏳
Технологии
Компонент	Технология
Frontend	Next.js 15, React 19, Tailwind CSS
Backend	FastAPI, SQLAlchemy, asyncpg
Database	PostgreSQL 16 + pgvector
LLM	OpenAI API + Anthropic API (чрез LLM Gateway)
Queue	Redis + RQ
Storage	MinIO (S3-compatible)
OCR	Tesseract (+ bul language pack)
DOCX	python-docx / docxtpl
Dev	GitHub Codespaces + Copilot
Спецификация v1.3
Пълната архитектурна спецификация е в docs/. Ключови документи:

TP_AI_Agent_Prompt_Architecture_v1.3.docx — промпт и архитектура
TP_AI_Пътна_карта_и_Насоки.docx — пътна карта за разработка
