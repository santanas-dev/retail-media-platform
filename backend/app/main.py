"""
FastAPI application entry point.
Retail Media Platform — multichannel digital signage management.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import check_db_connection
from app.domains.media.storage import ensure_bucket as ensure_media_bucket
from app.domains.identity.router import router as identity_router
from app.domains.organization.router import router as organization_router
from app.domains.channels.router import router as channels_router
from app.domains.advertisers.router import router as advertisers_router
from app.domains.media.router import router as media_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown logic."""
    settings = get_settings()
    await check_db_connection(settings)
    await ensure_media_bucket()
    yield


app = FastAPI(
    title="Retail Media Platform",
    description="Multichannel retail media management platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(identity_router)
app.include_router(organization_router)
app.include_router(channels_router)
app.include_router(advertisers_router)
app.include_router(media_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "0.1.0",
        "db": "connected",
    }
