from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.routers import (
    projects,
    files,
    agents,
    export,
    understanding,
    content_plan,
    criteria,
    consistency,
    plan_audit,
)

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

app = FastAPI(
    title="TP AI - Технически Предложения",
    version="0.1.0",
    description="AI асистент за съставяне на технически предложения за обществени поръчки",
    redirect_slashes=False,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Allow any GitHub Codespaces forwarded-port URL (e.g. <name>-3000.app.github.dev)
    allow_origin_regex=r"https://.*-\d+\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(export.router, prefix="/api/v1/export", tags=["export"])
app.include_router(
    understanding.router,
    prefix="/api/v1/understanding",
    tags=["understanding"],
)
app.include_router(
    content_plan.router,
    prefix="/api/v1/content-plan",
    tags=["content-plan"],
)
app.include_router(
    criteria.router,
    prefix="/api/v1/criteria",
    tags=["criteria"],
)
app.include_router(
    consistency.router,
    prefix="/api/v1/consistency",
    tags=["consistency"],
)
app.include_router(
    plan_audit.router,
    prefix="/api/v1/plan-audit",
    tags=["plan-audit"],
)


@app.get("/api/v1/capabilities", tags=["capabilities"])
async def capabilities():
    """Expose the active pipeline so the UI loads only available features.

    v2-only endpoints answer 404 when the v1 pipeline is active. Without this
    explicit signal the UI cannot tell "feature disabled" from a real error,
    and a disabled-feature 404 could hide existing generated text.
    """
    from app.core.model_policy import (
        ModelPolicyError,
        policy_mode,
        policy_version,
        validate_policy,
    )

    v2_enabled = settings.generation_pipeline == "v2"
    try:
        model_policy: dict = {
            "mode": policy_mode(),
            "version": policy_version(),
            "roles": {
                role: {
                    key: profile[key]
                    for key in ("provider", "model", "effort", "critical")
                }
                for role, profile in validate_policy().items()
            },
        }
    except ModelPolicyError as exc:
        model_policy = {"error": str(exc)}
    return {
        "generation_pipeline": settings.generation_pipeline,
        "features": {
            "understanding": v2_enabled,
            "content_plan": v2_enabled,
            "criteria_verification": v2_enabled,
            "consistency_check": v2_enabled,
            "plan_audit": v2_enabled,
        },
        "plan_audit_required": v2_enabled and settings.plan_audit_required,
        "model_policy": model_policy,
    }


@app.get("/health")
async def health():
    checks: dict = {"status": "ok", "db": "ok", "redis": "ok"}

    # Database liveness
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        checks["db"] = f"error: {e}"
        checks["status"] = "degraded"

    # Redis liveness
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
    except Exception as e:
        checks["redis"] = f"error: {e}"
        checks["status"] = "degraded"

    return checks
