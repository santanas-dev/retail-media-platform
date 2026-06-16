# Advertisers & Commercial Base API

## Overview

The Advertisers domain provides the commercial foundation for the Retail Media Platform. It manages advertisers (legal entities), their brands, contracts, and orders before campaigns are built on top.

## Entities

| Entity | Description |
|--------|-------------|
| **Advertiser** | Legal entity or client placing advertising |
| **Brand** | Trademark within an advertiser (one advertiser can have many brands) |
| **Contract** | Legal basis for placement with date range and amount limit |
| **Order** | Commercial placement request/package, links advertiser, brand, and contract |

## Endpoints

### Advertisers

| Method | Path | Permission |
|--------|------|-----------|
| GET | /api/advertisers | advertisers.read |
| POST | /api/advertisers | advertisers.manage |
| GET | /api/advertisers/{id} | advertisers.read |
| PUT | /api/advertisers/{id} | advertisers.manage |

### Brands

| Method | Path | Permission | Filters |
|--------|------|-----------|---------|
| GET | /api/brands | brands.read | ?advertiser_id= |
| POST | /api/brands | brands.manage | |
| GET | /api/brands/{id} | brands.read | |
| PUT | /api/brands/{id} | brands.manage | |

### Contracts

| Method | Path | Permission | Filters |
|--------|------|-----------|---------|
| GET | /api/contracts | contracts.read | ?advertiser_id= & ?status= |
| POST | /api/contracts | contracts.manage | |
| GET | /api/contracts/{id} | contracts.read | |
| PUT | /api/contracts/{id} | contracts.manage | |

### Orders

| Method | Path | Permission | Filters |
|--------|------|-----------|---------|
| GET | /api/orders | orders.read | ?advertiser_id= & ?brand_id= & ?contract_id= & ?status= |
| POST | /api/orders | orders.manage | |
| GET | /api/orders/{id} | orders.read | |
| PUT | /api/orders/{id} | orders.manage | |

## Statuses

| Entity | Allowed values |
|--------|---------------|
| Advertiser | active, inactive, blocked |
| Brand | active, inactive |
| Contract | draft, active, expired, closed, cancelled |
| Order | draft, pending, approved, in_progress, completed, cancelled |

Status transitions are not enforced on this step — any allowed status can be set via PUT.

## Validation Rules

- `inn` — string, max 12 chars (not a number, supports leading zeros)
- `kpp` — string, max 9 chars
- `currency` — 3 uppercase letters, default RUB
- `valid_from` must be <= `valid_to`
- `planned_start_date` must be <= `planned_end_date`
- `brand_id` must belong to order's `advertiser_id`
- `contract_id` must belong to order's `advertiser_id`
- Creating brand/contract/order with nonexistent `advertiser_id` returns 404

## Unique Constraints

- `advertisers.inn` — unique (nullable, multiple NULLs allowed)
- `brands.(advertiser_id, name)` — brand name unique per advertiser
- `contracts.(advertiser_id, number)` — number unique per advertiser
- `orders.(advertiser_id, number)` — number unique per advertiser

## Foreign Keys

All FK use `ON DELETE RESTRICT` — parent entities cannot be deleted while referenced.

## Permissions (30 total)

8 new permissions added:
- advertisers.read, advertisers.manage
- brands.read, brands.manage
- contracts.read, contracts.manage
- orders.read, orders.manage

Role matrix:

| Role | Advertisers | Brands | Contracts | Orders |
|------|:----------:|:------:|:---------:|:------:|
| system_admin | read+manage | read+manage | read+manage | read+manage |
| ad_manager | read+manage | read+manage | read+manage | read+manage |
| approver | read | read | read | read |
| analyst | read | read | read | read |
| security_admin | read | read | read | read |
| operations | read | — | — | — |
| advertiser | — | — | — | — |
| device_service | — | — | — | — |
