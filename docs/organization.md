# Organization Domain

## Overview

Manages the retail organizational structure: branches, clusters, and stores.

## Tables

| Table | Description | Key fields |
|-------|-------------|------------|
| `branches` | Geographic/organizational branch | code (unique), timezone, is_active |
| `clusters` | Group of stores within a branch | branch_id (FK), is_active |
| `stores` | Individual retail store | code (unique), cluster_id (FK), address, timezone, is_active |

## API

| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/branches` | organization.read |
| POST | `/api/branches` | organization.manage |
| GET | `/api/branches/{id}` | organization.read |
| PUT | `/api/branches/{id}` | organization.manage |
| GET | `/api/clusters?branch_id=` | organization.read |
| POST | `/api/clusters` | organization.manage |
| GET | `/api/clusters/{id}` | organization.read |
| PUT | `/api/clusters/{id}` | organization.manage |
| GET | `/api/stores?cluster_id=&branch_id=` | organization.read |
| POST | `/api/stores` | organization.manage |
| GET | `/api/stores/{id}` | organization.read |
| PUT | `/api/stores/{id}` | organization.manage |

## Code format

All `code` fields must match `^[a-z0-9_-]+$` (lowercase Latin, digits, underscore, hyphen).
