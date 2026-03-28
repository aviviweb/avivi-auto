import asyncio

from avivi_master.db import Base, engine


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def run_init() -> None:
    asyncio.run(init_models())


if __name__ == "__main__":
    run_init()
