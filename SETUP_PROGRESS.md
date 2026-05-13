# Setup Progress

## What was done

- Created `docker-compose.yml` — production Docker Compose (no hot-reload, built images, 2 API workers)
- Created `apps/web/Dockerfile` — multi-stage Next.js production build
- Modified `apps/web/next.config.ts` — added `output: "standalone"` required by the Dockerfile
- Created `scripts/deploy.sh` — server-side bash deploy script (kept for reference)
- Created `scripts/deploy.ps1` — server-side PowerShell deploy script (used on this Windows server)
- Created `.github/workflows/deploy.yml` — GitHub Actions: auto-deploys on every push to main via SSH
- Configured git identity (user.email: ai@raicommerce.bg / user.name: Admin)
- Copied `.env` from old app folder — all keys/passwords already set
- Installed OpenSSH Server on this Windows machine
- Generated SSH deploy key pair at `C:\Users\Admin\.ssh\github_deploy`
- Added public key to `authorized_keys`
- Added GitHub Actions secrets: SERVER_HOST, SERVER_USER, SSH_PRIVATE_KEY
- Installed Docker Desktop
- Enabled Docker auto-start on Windows login via registry
- Committed and pushed all files to: https://github.com/GitRaicommerce/Agent_Technicheski_predlozheniya

## Server details
- Public IP: 92.247.16.162
- Windows user: Admin
- Repo path: C:\Users\Admin\Desktop\Agent_Technicheski_predlozheniya-main
- SSH key: C:\Users\Admin\.ssh\github_deploy

## What is left to do

### 1. Enable virtualization and restart
Run in PowerShell as Admin, then restart:
```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
dism.exe /online /enable-feature /featurename:Microsoft-Hyper-V-All /all /norestart
Restart-Computer
```
If Docker still shows "Virtualization support not detected" after restart, enable VT-x/AMD-V in BIOS.

### 2. First deploy (after Docker is running)
```powershell
cd C:\Users\Admin\Desktop\Agent_Technicheski_predlozheniya-main
docker compose up -d --wait
docker compose exec -T api alembic upgrade head
```

### 3. Verify it works
- Web: http://localhost:3000
- API health: http://localhost:8000/health
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001

### 4. Test auto-deploy
Make any small change, push to main, watch the Actions tab at:
https://github.com/GitRaicommerce/Agent_Technicheski_predlozheniya/actions

### 5. Import old data (optional — when developer provides it)
```powershell
# Import database
Get-Content backup.sql | docker compose exec -T postgres psql -U tpai tpai

# Import MinIO files
docker cp .\minio-backup\. (docker compose ps -q minio):/data
docker compose restart minio
```
