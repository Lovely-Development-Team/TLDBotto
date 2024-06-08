import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import arrow
import dateutil.parser
import discord
from apscheduler import events
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from botto import reactions
from .date_helpers import is_naive
from .models import Reminder
from .storage import TimezoneStorage
from .storage.reminder_storage import ReminderStorage

log = logging.getLogger(__name__)


class ReminderManager:
    def __init__(
        self,
        config: dict,
        scheduler: AsyncIOScheduler,
        storage: ReminderStorage,
        reactions: reactions.Reactions,
        timezones: TimezoneStorage,
    ):
        self.config = config
        self.scheduler = scheduler
        self.storage = storage
        self.reactions = reactions
        self.timezones = timezones
        self.missed_job_ids = []
        self.get_channel_func = None

        initial_refresh_run = datetime.utcnow() + timedelta(seconds=5)
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
                        "message_id": reminder.msg_id,
                        "channel_id": reminder.channel_id,
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
                    "message_id": reminder.msg_id,
                    "channel_id": reminder.channel_id,
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
        self, reminder_id: str, notes: str, message_id: str, channel_id: str
    ):
        log.info(f"Sending reminder '{reminder_id}': {notes}")

        reminder_text = f"Reminder: {notes.strip()}"
        if channel_id := channel_id:
            if channel := await self.get_channel_func(channel_id):
                async with channel.typing():
                    message = None
                    if message_id := message_id:
                        message = await channel.fetch_message(message_id)
                    if message:
                        await message.reply(reminder_text, tts=True)
                    else:
                        await channel.send(reminder_text, tts=True)
            else:
                log.warning(f"Unable to send reminder: Channel {channel_id} not found.")
        else:
            channel = await self.get_channel_func(self.config["reminder_channel"])
            async with channel.typing():
                await channel.send(reminder_text, tts=True)

        if not reminder_id.endswith("_advance"):
            await self.storage.remove_reminder(reminder_id)
        await self.cleanup_missed_reminders()

    async def parse_reminder_time(
        self, timestamp: str, requester: discord.Member
    ) -> datetime:
        try:
            parsed_date = dateutil.parser.parse(timestamp)
            was_parsed_date_naive = is_naive(parsed_date)
            parsed_date = arrow.get(parsed_date)
            if was_parsed_date_naive:
                if tlder := await self.timezones.get_tlder(str(requester.id)):
                    tldr_timezone = await self.timezones.get_timezone(tlder.timezone_id)
                    log.debug(f"Parsed reminder datetime: {parsed_date}")
                    parsed_date = arrow.get(parsed_date).replace(
                        tzinfo=tldr_timezone.name
                    )
                    log.debug(f"Timezone-adjusted reminder datetime: {parsed_date}")
                else:
                    log.warning(f"Found no TLDer: {requester}")
            near_now = arrow.utcnow() + timedelta(minutes=1)
            if parsed_date.to(timezone.utc) < near_now:
                raise TimeTravelError(parsed_date.datetimed, near_now.datetime)
            return parsed_date.datetime
        except (TypeError, dateutil.parser.ParserError) as error:
            raise ReminderParsingError() from error

    async def build_reminder_description(self, reminder: Reminder):
        channel_text = ""
        if channel_id := reminder.channel_id:
            if channel := await self.get_channel_func(channel_id):
                channel_text = f" in {channel.mention}"

        advance_reminder_string = (
            " with 15 minute reminder" if reminder.remind_15_minutes_before else ""
        )
        return (
            f"'{reminder.notes}' at "
            f"{reminder.date.strftime('%a %H:%M:%S %Z')}{advance_reminder_string}{channel_text}. "
            f"Reference `{reminder.id}`."
        )

    async def build_reminder_message(self, reminder: Reminder):
        return f"Added reminder {await self.build_reminder_description(reminder)}"

    async def create_reminder(
        self,
        reminder_time: datetime,
        text: str,
        msg_id,
        channel_id,
        requester_id: str,
        force_advance_reminder: bool = False,
    ):
        advance_reminder = force_advance_reminder or "🕰" in text
        log.debug(f"Creating reminder. Advance warning: {advance_reminder}")
        reminder_notes = text.replace("🕰\ufe0f", "").strip()
        created_reminder = await self.storage.add_reminder(
            reminder_time,
            notes=reminder_notes,
            msg_id=str(msg_id) if msg_id else None,
            channel_id=str(channel_id) if channel_id else None,
            requester_id=requester_id,
            advance_reminder=advance_reminder,
        )
        log.info(f"Created reminder: {created_reminder}")
        return created_reminder

    async def add_reminder_message(
        self, reply_to: discord.Message, timestamp: str, text: str
    ):
        log.info(f"Reminder request from: {reply_to.author}")
        async with reply_to.channel.typing():
            try:
                parsed_date = await self.parse_reminder_time(timestamp, reply_to.author)
            except TimeTravelError as error:
                log.error("Reminder request expected time travel")
                await asyncio.gather(
                    self.reactions.reject(reply_to), reply_to.reply(error.message)
                )
            except ReminderParsingError:
                log.error("Failed to process reminder time", exc_info=True)
                await asyncio.gather(
                    self.reactions.reject(reply_to),
                    reply_to.reply(f"I'm sorry, I was unable to process this time 😢."),
                )
                return
            created_reminder = await self.create_reminder(
                reminder_time=parsed_date,
                text=text,
                msg_id=reply_to.id,
                channel_id=reply_to.channel.id,
            )
            await reply_to.reply(await self.build_reminder_message(created_reminder))
        await asyncio.gather(self.refresh_reminders(), self.cleanup_missed_reminders())

    async def add_reminder_slash(
        self,
        requester: discord.Member,
        timestamp: str,
        text: str,
        channel: discord.TextChannel,
        advance_reminder=False,
    ):
        log.info(f"Reminder request from: {requester}")
        parsed_date = await self.parse_reminder_time(timestamp, requester)
        created_reminder = await self.create_reminder(
            reminder_time=parsed_date,
            text=f"{requester.mention}" + text,
            msg_id=None,
            channel_id=channel.id,
            requester_id=str(requester.id),
            force_advance_reminder=advance_reminder,
        )
        await asyncio.gather(self.refresh_reminders(), self.cleanup_missed_reminders())
        return created_reminder

    async def list_reminders(
        self,
        guild: discord.Guild,
        channel: Optional[discord.TextChannel] = None,
    ) -> list[Reminder]:
        reminders_for_guild: list[Reminder] = []
        async for reminder in self.storage.retrieve_reminders():
            reminder_channel: Optional[discord.TextChannel] = (
                await self.get_channel_func(reminder.channel_id)
            )
            if not reminder_channel or reminder_channel.guild.id != guild.id:
                continue
            if channel is not None and reminder_channel.id != channel.id:
                continue
            reminders_for_guild.append(reminder)
        return reminders_for_guild


class ReminderError(Exception):
    pass


class TimeTravelError(ReminderError):
    def __init__(self, parsed_date: datetime, command_time: datetime):
        super().__init__()
        self.parsed_date = parsed_date
        self.command_time = command_time

    @property
    def parsed_date_string(self):
        return self.parsed_date.strftime("%a %H:%M:%S %Z")

    @property
    def command_time_string(self):
        return self.command_time.strftime("%a %H:%M:%S")

    @property
    def message(self):
        return (
            "Reminder data parsed as {parsed_date} but it is now {now}.\n"
            "I'm sorry, time travel is difficult 😢."
        ).format(
            parsed_date=self.parsed_date_string,
            now=self.command_time_string,
        )


class ReminderParsingError(ReminderError):
    pass
