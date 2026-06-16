"""
Organization domain: Pydantic schemas.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

CODE_PATTERN = r"^[a-z0-9_-]+$"


# ── Branch ────────────────────────────────────────────────────────────────

class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50, pattern=CODE_PATTERN)
    timezone: str = Field(default="Europe/Moscow", max_length=50)


class BranchUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    timezone: str | None = Field(None, max_length=50)
    is_active: bool | None = None


class BranchResponse(BaseModel):
    id: UUID
    name: str
    code: str
    timezone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Cluster ───────────────────────────────────────────────────────────────

class ClusterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    branch_id: UUID


class ClusterUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    is_active: bool | None = None


class ClusterResponse(BaseModel):
    id: UUID
    name: str
    branch_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Store ─────────────────────────────────────────────────────────────────

class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50, pattern=CODE_PATTERN)
    cluster_id: UUID
    address: str | None = None
    timezone: str = Field(default="Europe/Moscow", max_length=50)


class StoreUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = None
    timezone: str | None = Field(None, max_length=50)
    is_active: bool | None = None


class StoreResponse(BaseModel):
    id: UUID
    name: str
    code: str
    cluster_id: UUID
    address: str | None
    timezone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
