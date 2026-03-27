from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.config import SCHEDULER_TIMEZONE
from backend.database import claim_scheduler_run, get_unpaid_students, purge_expired_blocklist
from backend.logging_config import get_logger
from backend.whatsapp import send_template

logger = get_logger("scheduler")
timezone_local = ZoneInfo(SCHEDULER_TIMEZONE)
scheduler = AsyncIOScheduler(timezone=timezone_local)

REMINDER_MORNING = CronTrigger(hour=9, minute=0, timezone=timezone_local)
REMINDER_EVENING = CronTrigger(hour=18, minute=0, timezone=timezone_local)
PURGE_TRIGGER = CronTrigger(hour=0, minute=15, timezone=timezone_local)


def _next_run(trigger: CronTrigger, now: datetime) -> datetime:
    return trigger.get_next_fire_time(now, now) or now


async def _run_guarded(job_name: str, trigger: CronTrigger, action):
    now = datetime.now(timezone.utc)
    claimed = await claim_scheduler_run(job_name, _next_run(trigger, now.astimezone(timezone_local)).astimezone(timezone.utc), now)
    if not claimed:
        logger.info("scheduler_skip", action=job_name)
        return
    await action()


async def send_fee_reminders() -> None:
    students = await get_unpaid_students()
    if not students:
        logger.info("reminders_noop", action="send_fee_reminders")
        return

    sent = 0
    failed = 0
    for student in students:
        response = send_template(
            to=student["phone"],
            template_name="fees_remainder1",
            params=[
                student["name"],
                str(int(student["fee_amount"])),
                student["batch"],
                student["fee_due_date"],
            ],
        )
        if response.ok:
            sent += 1
        else:
            failed += 1
    logger.info("reminders_completed", action="send_fee_reminders", sent=sent, failed=failed, total=len(students))


async def reminder_job(trigger: CronTrigger, job_name: str) -> None:
    await _run_guarded(job_name, trigger, send_fee_reminders)


async def purge_blocklist_job() -> None:
    deleted = await purge_expired_blocklist()
    logger.info("token_blocklist_purged", action="purge_blocklist", deleted=deleted)


async def purge_job(trigger: CronTrigger, job_name: str) -> None:
    await _run_guarded(job_name, trigger, purge_blocklist_job)


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(reminder_job, REMINDER_MORNING, args=[REMINDER_MORNING, "fee_reminders_09_00"], id="fee_reminders_09_00", replace_existing=True)
    scheduler.add_job(reminder_job, REMINDER_EVENING, args=[REMINDER_EVENING, "fee_reminders_18_00"], id="fee_reminders_18_00", replace_existing=True)
    scheduler.add_job(purge_job, PURGE_TRIGGER, args=[PURGE_TRIGGER, "purge_blocklist_daily"], id="purge_blocklist_daily", replace_existing=True)
    scheduler.start()
    logger.info("scheduler_started", action="scheduler_start")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped", action="scheduler_stop")
