from sqlalchemy import Integer, Column
from sqlalchemy.orm import relationship

from botto.models import Base


class Meal(Base):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meal_text = relationship("MealText")
    meal_time = relationship("MealTime")
    meal_emoji = relationship("MealEmoji")
