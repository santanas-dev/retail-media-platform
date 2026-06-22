"""
Hierarchy domain: idempotent seed — one-KSO pilot synthetic data (Step 37.1).

Creates synthetic demo entities for development/testing:
  - Branch:  demo_branch_north
  - Cluster: demo_cluster_001
  - Store:   demo_store_001
  - KSO:     demo_kso_001

ALL VALUES ARE SYNTHETIC. No real store/device/address data.
Idempotent — safe to run multiple times.

Usage:
    cd backend
    INITIAL_ADMIN_PASSWORD=*** python -m app.domains.hierarchy.seed
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_engine, get_session_factory
from app.domains.organization import models as org_models
from app.domains.hierarchy import models as hierarchy_models

# Synthetic one-KSO pilot values
DEMO_BRANCH = {
    "name": "Демо-филиал Север",
    "code": "demo_branch_north",
    "timezone": "Europe/Moscow",
}
DEMO_CLUSTER = {
    "name": "Демо-кластер 001",
    "code": "demo_cluster_001",
}
DEMO_STORE = {
    "name": "Демо-магазин 001",
    "code": "demo_store_001",
    "address": "ул. Демонстрационная, д.1 (синтетический адрес)",
    "format": "supermarket",
}
DEMO_KSO = {
    "device_code": "demo_kso_001",
    "display_name": "Демо КСО 001",
    "status": "active",
    "runtime_version": "1.0.0-dev",
    "player_version": "1.0.0-dev",
    "sidecar_version": "1.0.0-dev",
    "state_adapter_version": "1.0.0-dev",
}


async def seed() -> None:
    """Run idempotent synthetic one-KSO pilot seed."""
    settings = get_settings()
    engine = get_engine(settings)

    async with engine.begin() as conn:
        # ── Branch ────────────────────────────────────────────────────
        branch_result = await conn.execute(
            pg_insert(org_models.Branch)
            .values(**DEMO_BRANCH)
            .on_conflict_do_nothing(index_elements=["code"])
            .returning(org_models.Branch.id, org_models.Branch.code)
        )
        branch_row = branch_result.fetchone()

        if branch_row is None:
            # Already exists — look up
            br = await conn.execute(
                select(org_models.Branch).where(
                    org_models.Branch.code == DEMO_BRANCH["code"]
                )
            )
            branch_row = br.fetchone()
        assert branch_row is not None, "Branch seed failed"

        branch_id = branch_row[0]
        print(f"Branch: {branch_row[1]} (id={branch_id})")

        # ── Cluster ───────────────────────────────────────────────────
        cluster_result = await conn.execute(
            pg_insert(org_models.Cluster)
            .values(
                name=DEMO_CLUSTER["name"],
                code=DEMO_CLUSTER["code"],
                branch_id=branch_id,
            )
            .on_conflict_do_nothing(
                index_elements=["branch_id", "code"]
            )
            .returning(org_models.Cluster.id, org_models.Cluster.code)
        )
        cluster_row = cluster_result.fetchone()

        if cluster_row is None:
            cl = await conn.execute(
                select(org_models.Cluster).where(
                    org_models.Cluster.branch_id == branch_id,
                    org_models.Cluster.code == DEMO_CLUSTER["code"],
                )
            )
            cluster_row = cl.fetchone()
        assert cluster_row is not None, "Cluster seed failed"

        cluster_id = cluster_row[0]
        print(f"Cluster: {cluster_row[1]} (id={cluster_id})")

        # ── Store ─────────────────────────────────────────────────────
        store_result = await conn.execute(
            pg_insert(org_models.Store)
            .values(
                name=DEMO_STORE["name"],
                code=DEMO_STORE["code"],
                cluster_id=cluster_id,
                address=DEMO_STORE["address"],
                format=DEMO_STORE["format"],
                status="active",
            )
            .on_conflict_do_nothing(index_elements=["code"])
            .returning(org_models.Store.id, org_models.Store.code)
        )
        store_row = store_result.fetchone()

        if store_row is None:
            st = await conn.execute(
                select(org_models.Store).where(
                    org_models.Store.code == DEMO_STORE["code"]
                )
            )
            store_row = st.fetchone()
        assert store_row is not None, "Store seed failed"

        store_id = store_row[0]
        print(f"Store: {store_row[1]} (id={store_id})")

        # ── KSO Device ────────────────────────────────────────────────
        device_result = await conn.execute(
            pg_insert(hierarchy_models.KsoDevice)
            .values(
                store_id=store_id,
                device_code=DEMO_KSO["device_code"],
                display_name=DEMO_KSO["display_name"],
                status=DEMO_KSO["status"],
                runtime_version=DEMO_KSO["runtime_version"],
                player_version=DEMO_KSO["player_version"],
                sidecar_version=DEMO_KSO["sidecar_version"],
                state_adapter_version=DEMO_KSO["state_adapter_version"],
            )
            .on_conflict_do_nothing(index_elements=["device_code"])
            .returning(
                hierarchy_models.KsoDevice.id,
                hierarchy_models.KsoDevice.device_code,
            )
        )
        device_row = device_result.fetchone()

        if device_row is None:
            dev = await conn.execute(
                select(hierarchy_models.KsoDevice).where(
                    hierarchy_models.KsoDevice.device_code == DEMO_KSO["device_code"]
                )
            )
            device_row = dev.fetchone()
        assert device_row is not None, "KSO device seed failed"

        print(f"KSO Device: {device_row[1]} (id={device_row[0]})")

    print("One-KSO pilot seed complete.")
    print(f"  Branch:  {DEMO_BRANCH['code']}")
    print(f"  Cluster: {DEMO_CLUSTER['code']}")
    print(f"  Store:   {DEMO_STORE['code']}")
    print(f"  KSO:     {DEMO_KSO['device_code']}")


def main():
    """Entry point for `python -m app.domains.hierarchy.seed`."""
    asyncio.run(seed())


if __name__ == "__main__":
    main()
