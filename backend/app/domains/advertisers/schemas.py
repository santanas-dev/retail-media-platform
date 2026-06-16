"""Advertisers & Commercial Base domain: Pydantic schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ── Shared fields ─────────────────────────────────────────────────────────

CURRENCY_PATTERN = r"^[A-Z]{3}$"


# ── Advertiser ─────────────────────────────────────────────────────────────

class AdvertiserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(None, max_length=500)
    inn: str | None = Field(None, min_length=1, max_length=12)
    kpp: str | None = Field(None, min_length=1, max_length=9)
    status: str = Field(default="active", pattern=r"^(active|inactive|blocked)$")
    contacts_json: dict = Field(default_factory=dict)
    comment: str | None = None


class AdvertiserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    legal_name: str | None = Field(None, max_length=500)
    inn: str | None = Field(None, min_length=1, max_length=12)
    kpp: str | None = Field(None, min_length=1, max_length=9)
    status: str | None = Field(None, pattern=r"^(active|inactive|blocked)$")
    contacts_json: dict | None = None
    comment: str | None = None


class AdvertiserResponse(BaseModel):
    id: UUID
    name: str
    legal_name: str | None
    inn: str | None
    kpp: str | None
    status: str
    contacts_json: dict
    comment: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Brand ──────────────────────────────────────────────────────────────────

class BrandCreate(BaseModel):
    advertiser_id: UUID
    name: str = Field(min_length=1, max_length=255)
    category: str | None = Field(None, max_length=100)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")


class BrandUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    category: str | None = Field(None, max_length=100)
    status: str | None = Field(None, pattern=r"^(active|inactive)$")


class BrandResponse(BaseModel):
    id: UUID
    advertiser_id: UUID
    name: str
    category: str | None
    status: str
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Contract ───────────────────────────────────────────────────────────────

class ContractCreate(BaseModel):
    advertiser_id: UUID
    number: str = Field(min_length=1, max_length=100)
    valid_from: date
    valid_to: date
    status: str = Field(
        default="draft",
        pattern=r"^(draft|active|expired|closed|cancelled)$",
    )
    amount_limit: float | None = None
    currency: str = Field(default="RUB", pattern=CURRENCY_PATTERN)
    comment: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "ContractCreate":
        if self.valid_from > self.valid_to:
            raise ValueError("valid_from must be <= valid_to")
        return self


class ContractUpdate(BaseModel):
    number: str | None = Field(None, min_length=1, max_length=100)
    valid_from: date | None = None
    valid_to: date | None = None
    status: str | None = Field(
        None,
        pattern=r"^(draft|active|expired|closed|cancelled)$",
    )
    amount_limit: float | None = None
    currency: str | None = Field(None, pattern=CURRENCY_PATTERN)
    comment: str | None = None


class ContractResponse(BaseModel):
    id: UUID
    advertiser_id: UUID
    number: str
    valid_from: date
    valid_to: date
    status: str
    amount_limit: float | None
    currency: str
    comment: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Order ──────────────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    advertiser_id: UUID
    brand_id: UUID | None = None
    contract_id: UUID | None = None
    number: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    status: str = Field(
        default="draft",
        pattern=r"^(draft|pending|approved|in_progress|completed|cancelled)$",
    )
    planned_budget: float | None = None
    currency: str = Field(default="RUB", pattern=CURRENCY_PATTERN)
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    comment: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "OrderCreate":
        if (
            self.planned_start_date is not None
            and self.planned_end_date is not None
            and self.planned_start_date > self.planned_end_date
        ):
            raise ValueError("planned_start_date must be <= planned_end_date")
        return self


class OrderUpdate(BaseModel):
    brand_id: UUID | None = None
    contract_id: UUID | None = None
    number: str | None = Field(None, min_length=1, max_length=100)
    name: str | None = Field(None, min_length=1, max_length=500)
    status: str | None = Field(
        None,
        pattern=r"^(draft|pending|approved|in_progress|completed|cancelled)$",
    )
    planned_budget: float | None = None
    currency: str | None = Field(None, pattern=CURRENCY_PATTERN)
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    comment: str | None = None


class OrderResponse(BaseModel):
    id: UUID
    advertiser_id: UUID
    brand_id: UUID | None
    contract_id: UUID | None
    number: str
    name: str
    status: str
    planned_budget: float | None
    currency: str
    planned_start_date: date | None
    planned_end_date: date | None
    comment: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
