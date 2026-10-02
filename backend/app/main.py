"""FastAPI composition root. Schema changes and provisioning are explicit CLI operations."""

from fastapi import FastAPI

from app.accounts import router as accounts_router
from app.config import settings
from app.http import install_http_controls
from app.routes import (
    candidates,
    communications,
    health,
    interviews,
    jobs,
    offers,
    organization,
    public,
    resumes,
    tasks,
)

app = FastAPI(
    title="HireFlow API",
    version="1.0.0",
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None,
    openapi_url=None if settings.environment == "production" else "/openapi.json",
)
install_http_controls(app)
app.include_router(accounts_router)
app.include_router(health.router)
app.include_router(candidates.router)
app.include_router(jobs.router)
app.include_router(public.router)
app.include_router(interviews.router)
app.include_router(offers.router)
app.include_router(tasks.router)
app.include_router(organization.router)
app.include_router(communications.router)
app.include_router(resumes.router)
