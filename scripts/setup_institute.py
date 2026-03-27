import asyncio
import os

from backend.database import create_institute
from backend.db import run_migrations
from backend.logging_config import configure_logging, get_logger

configure_logging()
logger = get_logger("setup_institute")
run_migrations()


async def main() -> None:
    name = os.getenv("NEW_INSTITUTE_NAME")
    username = os.getenv("NEW_INSTITUTE_USERNAME")
    password = os.getenv("NEW_INSTITUTE_PASSWORD")

    if name and username and password:
        created = await create_institute(name=name, username=username, password=password)
        logger.info("setup_institute_complete", action="setup_institute", username=username, created=created)
    else:
        logger.warning("setup_institute_missing_env", action="setup_institute")


if __name__ == "__main__":
    asyncio.run(main())
