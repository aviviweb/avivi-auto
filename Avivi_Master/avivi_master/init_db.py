import asyncio

from sqlalchemy import text

from avivi_master.db import Base, engine


def _migrate_sqlite_schema(sync_conn) -> None:
    """Add columns on existing DBs (SQLite)."""
    try:
        rows = sync_conn.execute(text("PRAGMA table_info(clients)")).fetchall()
    except Exception:
        return
    col_names = {r[1] for r in rows}
    if "agent_domain" not in col_names:
        sync_conn.execute(text("ALTER TABLE clients ADD COLUMN agent_domain VARCHAR(256) DEFAULT ''"))
    if "business_id" not in col_names:
        sync_conn.execute(text("ALTER TABLE clients ADD COLUMN business_id VARCHAR(64)"))

    try:
        rows_a = sync_conn.execute(text("PRAGMA table_info(audit_log)")).fetchall()
        col_a = {r[1] for r in rows_a}
        if "business_id" not in col_a:
            sync_conn.execute(text("ALTER TABLE audit_log ADD COLUMN business_id VARCHAR(64)"))
    except Exception:
        pass


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_sqlite_schema)


def run_init() -> None:
    asyncio.run(init_models())


if __name__ == "__main__":
    run_init()
