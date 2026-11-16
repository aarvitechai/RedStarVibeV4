"""Index help-centre articles for search and the assistant (idempotent; runs in the migrate step)."""

import asyncio

from app.core.database import dispose_engine, get_sessionmaker
from app.modules.search import service


async def main() -> None:
    async with get_sessionmaker()() as db:
        n = await service.index_help_docs(db)
    await dispose_engine()
    print(f"help docs indexed: {n} changed")


if __name__ == "__main__":
    asyncio.run(main())
