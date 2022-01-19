from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from botto.models import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    airtable_id = Column(String)
    discord_id = Column(String)
    name = Column(String)
    timezone_id = Column(Integer, ForeignKey("timezone.id"))
    timezone = relationship("Timezone", back_populates="users")
    reminder_requests = relationship("User", back_populates="request_user")
