from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import projects, files, agents, export

app = FastAPI(
    title="TP AI - Технически Предложения",
    version="0.1.0",
    description="AI асистент за съставяне на технически предложения за обществени поръчки",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(export.router, prefix="/api/v1/export", tags=["export"])


@app.get("/health")
async def health():
    return {"status": "ok"}
