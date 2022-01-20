from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from botto.models import Base


class TimeZone(Base):
    __tablename__ = "timezones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    users = relationship("User", back_populates="timezone")
