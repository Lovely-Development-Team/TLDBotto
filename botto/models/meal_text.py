from sqlalchemy import Integer, Column, String, Table, ForeignKey
from sqlalchemy.orm import relationship

from botto.models import Base

meal_time_text = Table(
    "meal_time_text",
    Base.metadata,
    Column("meal_time_id", ForeignKey("meal_time.id")),
    Column("meal_text_id", ForeignKey("meal_text.id")),
)


class MealText(Base):
    __tablename__ = "meal_texts"

    id = Column(Integer, primary_key=True)
    text = Column(String)
    meal_time = relationship(
        "MealTime", secondary=meal_time_text, back_populates="meal_texts"
    )
    server: relationship("Server", back_populates="meal_times")
