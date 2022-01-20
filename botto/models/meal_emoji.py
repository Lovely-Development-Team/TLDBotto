from sqlalchemy import Integer, Column, String, ForeignKey, Table
from sqlalchemy.orm import relationship

from botto.models import Base

meal_time_emoji = Table(
    "meal_time_emoji",
    Base.metadata,
    Column("meal_time_id", ForeignKey("meal_time.id")),
    Column("meal_emoji_id", ForeignKey("meal_emoji.id")),
)


class MealEmoji(Base):
    __tablename__ = "meal_emoji"

    id = Column(Integer, primary_key=True)
    text = Column(String)
    meal_time = relationship(
        "MealTime", secondary=meal_time_emoji, back_populates="meal_emoji"
    )
    server_id = Column(Integer, ForeignKey("server.id"))
    server = relationship("Server", back_populates="meal_emoji")
