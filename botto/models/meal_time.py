from sqlalchemy import Integer, Column, String, Time, ForeignKey
from sqlalchemy.orm import relationship

from botto.models import Base


class MealTime(Base):
    __tablename__ = "meal_times"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    start_time = Column(Time)
    end_time = Column(Time)
    meal_texts = relationship("MealText", back_populates="meal_time")
    meal_emoji = relationship("MealEmoji", back_populates="meal_emoji")
    server_id = Column(Integer, ForeignKey("server.id"))
    server: relationship("Server", back_populates="meal_times")
