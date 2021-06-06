import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import dateutil.parser
import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler import events

import reactions
from models import MessageAndChannel
from storage import ReminderStorage

log = logging.getLogger(__name__)


class ReminderManager:
    def __init__(
        self, config: dict, scheduler: AsyncIOScheduler, storage: ReminderStorage
    ):
        self.config = config
        self.scheduler = scheduler
        self.storage = storage
        self.missed_job_ids = []
        self.get_channel_func = None

        initial_refresh_run = datetime.now() + timedelta(seconds=5)
        scheduler.add_job(
            self.refresh_reminders,
            name="Refresh reminders",
            trigger="cron",
            hour="*/1",
            coalesce=True,
            next_run_time=initial_refresh_run,
        )

        scheduler.add_listener(self.handle_scheduler_event, events.EVENT_JOB_MISSED)

    def handle_scheduler_event(self, event: events.JobEvent):
        if job := self.scheduler.get_job(event.job_id):
            if job.name.startswith("Reminder:") and not event.job_id.endswith(
                "_advance"
            ):
                self.missed_job_ids.append(event.job_id)

    async def refresh_reminders(self):
        reminders_processed = 0
        async for reminder in self.storage.retrieve_reminders():
            if reminder.remind_15_minutes_before:
                self.scheduler.add_job(
                    self.send_reminder,
                    id=reminder.id + "_advance",
                    name=f"Reminder: {reminder.notes.strip()} in 15 minutes!",
                    trigger="date",
                    next_run_time=reminder.date - timedelta(minutes=15),
                    coalesce=True,
                    replace_existing=True,
                    kwargs={
                        "reminder_id": reminder.id + "_advance",
                        "notes": f"{reminder.notes.strip()} in 15 minutes!",
                        "message_and_channel": MessageAndChannel(
                            reminder.channel_id, reminder.msg_id
                        )
                        if reminder.channel_id and reminder.msg_id
                        else None,
                    },
                )
            self.scheduler.add_job(
                self.send_reminder,
                id=reminder.id,
                name=f"Reminder: {reminder.notes.strip()} now ({reminder.date})!",
                trigger="date",
                next_run_time=reminder.date,
                coalesce=True,
                replace_existing=True,
                kwargs={
                    "reminder_id": reminder.id,
                    "notes": f"{reminder.notes.strip()} now ({reminder.date})!",
                    "message_and_channel": MessageAndChannel(
                        reminder.channel_id, reminder.msg_id
                    )
                    if reminder.channel_id and reminder.msg_id
                    else None,
                },
            )
            reminders_processed += 1
        log.debug(f"Refreshed {reminders_processed} reminders")

    def start(self, get_channel_func: Callable):
        self.get_channel_func = get_channel_func
        if self.scheduler.state == 0:
            self.scheduler.start()

    @property
    def reminder_syntax(self) -> str:
        return "`@TLDBotto !reminder <datetime>. <message>`"

    async def cleanup_missed_reminders(self):
        log.info("Cleaning missed reminders")
        deletions = [
            self.storage.remove_reminder(job_id) for job_id in self.missed_job_ids
        ]
        await asyncio.gather(*deletions)
        log.info(f"Deleted job IDs: {self.missed_job_ids}")
        self.missed_job_ids = []

    async def send_reminder_syntax(self, message: discord.Message, **kwargs):
        log.info("Sending reminder syntax")
        await asyncio.gather(
            message.reply(f"Syntax for setting a reminder is: {self.reminder_syntax}"),
            self.cleanup_missed_reminders(),
        )

    async def send_reminder(
        self,
        reminder_id: str,
        notes: str,
        message_and_channel: Optional[MessageAndChannel],
    ):
        log.info(f"Sending reminder '{reminder_id}': {notes}")

        if message_and_channel := message_and_channel:
            if channel := await self.get_channel_func(message_and_channel.channel_id):
                async with channel.typing():
                    if message := await channel.fetch_message(
                        message_and_channel.msg_id
                    ):
                        await message.reply(f"Reminder: {notes.strip()}", tts=True)
        else:
            channel = await self.get_channel_func(self.config["reminder_channel"])
            async with channel.typing():
                await channel.send(f"Reminder: {notes.strip()}", tts=True)
                if not reminder_id.endswith("_advance"):
                    await self.storage.remove_reminder(reminder_id)
        await self.cleanup_missed_reminders()

    async def add_reminder(self, reply_to: discord.Message, timestamp: str, text: str):
        def get_now_datetime():
            if parsed_date.tzinfo and parsed_date.tzinfo.utcoffset(parsed_date):
                return datetime.now(timezone.utc)
            else:
                return datetime.utcnow()
        log.info(f"Reminder request from: {reply_to.author}")
        async with reply_to.channel.typing():
            try:
                parsed_date = dateutil.parser.parse(timestamp)
                parsed_date_string = parsed_date.strftime("%a %H:%M:%S %Z")
                near_now = get_now_datetime() + timedelta(minutes=1)
                if parsed_date < near_now:
                    await asyncio.gather(
                        reactions.reject(self.config["reactions"], reply_to),
                        reply_to.reply(
                            (
                                "Reminder data parsed as {parsed_date} but it is now {now}.\n"
                                "I'm sorry, time travel is difficult 😢."
                            ).format(
                                parsed_date=parsed_date_string,
                                now=near_now.strftime("%a %H:%M:%S"),
                            )
                        ),
                    )
                    return
            except (TypeError, dateutil.parser.ParserError):
                log.error("Failed to process reminder time", exc_info=True)
                await asyncio.gather(
                    reactions.reject(self.config["reactions"], reply_to),
                    reply_to.reply(f"I'm sorry, I was unable to process this time 😢."),
                )
                return
            advance_reminder = "🕰" in text
            log.info(f"Creating reminder. Advance warning: {advance_reminder}")
            reminder_notes = text.replace("🕰\ufe0f", "").strip()
            created_reminder = await self.storage.add_reminder(
                parsed_date,
                notes=reminder_notes,
                msg_id=str(reply_to.id),
                channel_id=str(reply_to.channel.id),
                advance_reminder=advance_reminder,
            )
            advance_reminder_string = (
                " with 15 minute reminder" if advance_reminder else ""
            )
            confirmation_message = (
                f"Added reminder '{reminder_notes}' at "
                f"{parsed_date_string}{advance_reminder_string}. Reference `{created_reminder.id}` "
            )
            await reply_to.reply(confirmation_message)
        await asyncio.gather(self.refresh_reminders(), self.cleanup_missed_reminders())
