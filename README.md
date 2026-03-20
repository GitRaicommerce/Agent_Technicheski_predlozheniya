# 🏗️ TP AI — Технически Предложения

AI асистент за съставяне на Технически предложения (ТП) за обществени поръчки за проектиране, инженеринг или изпълнение на СМР.

## Архитектура

- **Оркестратор + 6 специализирани LLM агента** (Структура, График, Чернова, Примери, Законодателство, Верификатор)
- **Детерминистичен ingest pipeline** — OCR / парсинг / chunking / pgvector ембединги, без LLM
- **Evidence tracking** — всяка генерирана секция е свързана с конкретни документни фрагменти
- **Pre-export gate** — блокира `.docx` експорт при липсваща информация или конфликти
- **LLM Gateway** — единен интерфейс за OpenAI GPT-4o + Anthropic Claude (сменяеми)
- **Закрепване на варианти** — потребителят избира кой от двата генерирани варианта влиза в документа

Пълна спецификация: `docs/TP_AI_Agent_Prompt_Architecture_v1.3.docx`

---

## Бърз старт (GitHub Codespaces)

### 1. Добавяне на API ключове

В GitHub → **Settings → Codespaces → Secrets**, добавете:

| Секрет              | Откъде                                      |
| ------------------- | ------------------------------------------- |
| `OPENAI_API_KEY`    | https://platform.openai.com/api-keys        |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys |

### 2. Стартиране на Codespace

Натиснете зеления бутон **"Code" → "Codespaces" → "Create codespace on main"**.

При първо стартиране (~3–5 мин) средата автоматично:

- Стартира всички Docker services (PostgreSQL 16 + pgvector, Redis, MinIO, API, Worker, Frontend)
- Прилага Alembic миграциите
- Инсталира npm зависимостите

### 3. Достъп

| Услуга            | URL                                             |
| ----------------- | ----------------------------------------------- |
| **Frontend**      | http://localhost:3000                           |
| **API Docs**      | http://localhost:8000/docs                      |
| **MinIO Console** | http://localhost:9001 (minioadmin / minioadmin) |

---

## Локална разработка (без Codespaces)

```bash
# 1. Копирайте .env и попълнете API ключовете
cp .env.example .env
# Отворете .env и добавете OPENAI_API_KEY и/или ANTHROPIC_API_KEY

# 2. Build на Docker образите (задължително при първо стартиране!)
docker compose -f docker-compose.dev.yml build

# 3. Стартирайте всички услуги
docker compose -f docker-compose.dev.yml up -d

# 4. Приложете DB миграциите
bash migrate.sh
```

> **Забележка:** Стъпка 2 (`build`) е задължителна при всяко `git clone` на ново място.
> Пропускането й води до `ModuleNotFoundError` и мълчаливо неработещ API.

---

## Тестове

```bash
cd services/api
pip install -r requirements.txt
python -m pytest tests/ -v
```

21 unit теста покриват: `/health` (с DB + Redis mocking), Projects CRUD, Files endpoints, Agents chat/outline.

---

## Структура на проекта

```
.devcontainer/          # GitHub Codespaces конфигурация
apps/web/               # Frontend (Next.js 15, React 19, Tailwind CSS 4)
services/
└── api/                # Backend (FastAPI + SQLAlchemy async)
    ├── app/
    │   ├── core/       # Config, DB, LLM Gateway, embedding, storage
    │   ├── routers/    # REST endpoints (projects, files, agents, export)
    │   ├── agents/     # LLM агенти + промпт шаблони
    │   ├── ingestion/  # Парсъри, OCR, chunking, RQ worker
    │   └── export/     # DOCX генерация (python-docx)
    ├── alembic/        # DB миграции (3 версии)
    └── tests/          # pytest unit тестове
packages/schemas/       # JSON схеми за агентски отговори
docs/                   # Спецификация и документация
```

---

## Технологии

| Компонент     | Технология                                     |
| ------------- | ---------------------------------------------- |
| Frontend      | Next.js 15, React 19, Tailwind CSS 4           |
| Backend       | FastAPI, SQLAlchemy 2 (async), asyncpg         |
| Database      | PostgreSQL 16 + pgvector (1536-dim embeddings) |
| LLM           | OpenAI GPT-4o + Anthropic Claude (LLM Gateway) |
| Queue         | Redis + RQ                                     |
| Storage       | MinIO (S3-compatible)                          |
| OCR           | Tesseract (bul + eng)                          |
| DOCX          | python-docx                                    |
| Schedule      | mpxj (Java/JRE) за .mpp файлове                |
| Rate limiting | slowapi (200/min глобален, 20/min за /chat)    |
| Dev           | GitHub Codespaces + GitHub Copilot             |

---

## Пътна карта

| Фаза | Описание                                                | Статус    |
| ---- | ------------------------------------------------------- | --------- |
| 0    | Scaffold + схеми + DB + ingest pipeline + embeddings    | ✅ Готово |
| 1    | Оркестратор + Структура + График + LLM history          | ✅ Готово |
| 2    | Чернова + Верификатор + Evidence lifecycle + закрепване | ✅ Готово |
| 3    | Pre-export gate + DOCX експорт + Outline UI             | ✅ Готово |
| 4    | Тестове + CI/CD + мащабиране                            | 🔄 В ход  |
