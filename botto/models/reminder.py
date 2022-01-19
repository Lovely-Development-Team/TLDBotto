from sqlalchemy import Integer, Column, DateTime, String, Boolean
from sqlalchemy.orm import relationship

from botto.models import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id: Column(Integer, primary_key=True)
    date: Column(DateTime)
    notes: Column(String)
    advance_warning: Column(Boolean)
    message_id: Column(String)
    channel_id: Column(String)
    server: relationship("Server", back_populates="reminders")