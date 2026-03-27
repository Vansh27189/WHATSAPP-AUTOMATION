import asyncio

from backend.db import run_migrations
from backend.logging_config import configure_logging
from backend.scheduler import send_fee_reminders

configure_logging()
run_migrations()


if __name__ == "__main__":
    asyncio.run(send_fee_reminders())