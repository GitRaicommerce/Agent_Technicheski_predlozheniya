# Setup Progress

## What was done

- Created `docker-compose.yml` — production Docker Compose (no hot-reload, built images, 2 API workers)
- Created `apps/web/Dockerfile` — multi-stage Next.js production build
- Modified `apps/web/next.config.ts` — added `output: "standalone"` required by the Dockerfile
- Created `scripts/deploy.sh` — server-side script: git pull → docker build → migrate
- Created `.github/workflows/deploy.yml` — GitHub Actions: auto-deploys on every push to main via SSH
- Configured git identity (user.email / user.name)
- Committed and pushed all files to: https://github.com/GitRaicommerce/Agent_Technicheski_predlozheniya

## What is left to do

### 1. Install Docker Desktop (requires restart)
```powershell
winget install Docker.DockerDesktop
```
After install, restart PC and confirm Docker is running (whale icon in system tray).

### 2. Create the .env file
Copy `env.txt` in the repo root as a reference and create a real `.env` file:
```powershell
cd C:\Users\Admin\Desktop\Agent_Technicheski_predlozheniya-main
copy env.txt .env
notepad .env
```
Fill in real values:
- POSTGRES_PASSWORD
- OPENAI_API_KEY or ANTHROPIC_API_KEY
- MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
- APP_SECRET_KEY (any random string)
- NEXT_PUBLIC_API_URL (e.g. http://localhost:8000 if running locally)

### 3. First deploy (run manually once)
```powershell
cd C:\Users\Admin\Desktop\Agent_Technicheski_predlozheniya-main
docker compose up -d --wait
docker compose exec -T api alembic upgrade head
```

### 4. Verify it works
- Web: http://localhost:3000
- API health: http://localhost:8000/health
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001

### 5. Set up auto-deploy via GitHub Actions (for a remote Linux server only)
Skip this if you are deploying locally on this Windows machine.

If you have a separate Linux server:
- Generate SSH deploy key on the server:
  ```bash
  ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy -N ""
  cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
  cat ~/.ssh/github_deploy   # copy this private key
  ```
- Add these secrets at https://github.com/GitRaicommerce/Agent_Technicheski_predlozheniya/settings/secrets/actions:

  | Secret            | Value                                      |
  |-------------------|--------------------------------------------|
  | SERVER_HOST       | Server IP address                          |
  | SERVER_USER       | SSH username (e.g. ubuntu)                 |
  | SSH_PRIVATE_KEY   | Contents of ~/.ssh/github_deploy           |
  | DEPLOY_PATH       | Path on server (e.g. /opt/tpai)            |

After this, every `git push origin main` from any machine will automatically deploy to the server.
