from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from botto.models import Base
from botto.models.enablement import user_enabled, user_enabler


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    airtable_id = Column(String, unique=True)
    discord_id = Column(String, unique=True)
    name = Column(String)
    timezone_id = Column(Integer, ForeignKey("timezone.id"))
    timezone = relationship("Timezone", back_populates="users")
    reminder_requests = relationship("Reminder", back_populates="request_user")
    enabled_purchase = relationship("Enablement", secondary=user_enabled, back_populates="enabler")
    enabled_recommend = relationship("Enablement", secondary=user_enabler, back_populates="enabled")
