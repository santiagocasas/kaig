import asyncio
import logging
import os

from . import flow
from .db import init_db
from .ingestion import ingestion_loop

logger = logging.getLogger(__name__)


async def main() -> None:
    db_name = os.environ.get("DB_NAME")
    if not db_name:
        raise ValueError("DB_NAME environment variable is not set")

    logger.info("Starting ingestion loop...")
    db = init_db(True, db_name)
    exe = flow.Executor(db)
    await ingestion_loop(exe)


if __name__ == "__main__":
    asyncio.run(main())
