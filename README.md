# TP AI

AI асистент за изготвяне на технически предложения за обществени поръчки в строителство, инженеринг и проектиране.

## Документация

- Основен инженерeн преглед: [docs/ENGINEERING_OVERVIEW.md](C:\Users\Admin\Agent_Technicheski_predlozheniya\docs\ENGINEERING_OVERVIEW.md)
- Продуктова спецификация: `docs/TP_AI_Agent_Prompt_Architecture_v1.3.docx`
- Пътна карта и насоки: `docs/TP_AI_Пътна_карта_и_Насоки_2026-02-11_240d50.docx`

`docs/ENGINEERING_OVERVIEW.md` е генериран файл и е източникът на истина за:

- реалните версии на основните технологии;
- структурата на repo-то;
- backend router-и и test inventory;
- docker услугите и CI automation.

## Стартиране

### Локално

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d
bash migrate.sh
```

На Windows най-стабилният старт е:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

Този script:

- пуска Docker стека;
- изчаква API и web приложението реално да станат достъпни;
- подгрява основните web routes, за да намали първоначалното забавяне при първи тест;
- отваря `http://localhost:3000` чак когато приложението е готово.

Достъп:

- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- MinIO Console: `http://localhost:9001`

### GitHub Codespaces

Добави `OPENAI_API_KEY` и/или `ANTHROPIC_API_KEY` в GitHub Codespaces secrets, после стартирай codespace върху `main`.

## Тестове

### Backend

```bash
cd services/api
pip install -r requirements.txt
python -m pytest tests/ -v
```

### Frontend

```bash
cd apps/web
npm ci
npx tsc --noEmit
npm run lint
```

## Автоматизация на документацията

Документацията се поддържа автоматично на две нива:

- `pre-commit` hook регенерира `docs/ENGINEERING_OVERVIEW.md` преди всеки commit;
- `pre-push` hook проверява дали няма нерегенерирани промени;
- GitHub Action при `push` регенерира документацията и я commit-ва обратно, ако е изостанала.

Ръчно регенериране:

```bash
py -3 scripts/generate_docs.py
```
