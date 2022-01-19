from sqlalchemy import Integer, Column, String
from sqlalchemy.orm import relationship

from botto.models import Base


class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    reminders = relationship("Reminder", back_populates="server")