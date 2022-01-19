from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String,
    DECIMAL,
    TIMESTAMP,
    VARCHAR,
    Table,
)
from sqlalchemy.orm import relationship

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
    date = Column(TIMESTAMP)
    message_link = Column(String)
    amount = Column(DECIMAL)
    currency = Column(VARCHAR)
