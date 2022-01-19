from datetime import datetime

from sqlalchemy import Column, Integer, Date, ForeignKey, String, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.testing.schema import Table

from botto.models import Base

user_enabler = Table(
    "user_enabler",
    Base.metadata,
    Column("user_id", ForeignKey("user.id")),
    Column("enablement_id", ForeignKey("enablement.id")),
)
user_enabled = Table(
    "user_enabled",
    Base.metadata,
    Column("user_id", ForeignKey("user.id")),
    Column("enablement_id", ForeignKey("enablement.id")),
)


class Enablement(Base):
    __tablename__ = "enablement"

    id = Column(Integer, primary_key=True)
    enabler = relationship("User", secondary=user_enabler, back_populates="enabler")
    enabled = relationship("User", secondary=user_enabled, back_populates="enabled")
    date = Column(Date, default=datetime.utcnow())
    message_link = Column(String)
    amount = Column(DECIMAL)
