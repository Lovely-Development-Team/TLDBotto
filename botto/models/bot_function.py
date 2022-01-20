from sqlalchemy import Integer, Column, String, ForeignKey, Table, Boolean
from sqlalchemy.orm import relationship

from botto.models import Base

server_bot_functions = Table(
    "server_bot_functions",
    Base.metadata,
    Column("bot_function_id", ForeignKey("bot_function.id")),
    Column("server_id", ForeignKey("server.id")),
)


class BotFunction(Base):
    __tablename__ = "meal_emoji"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    description = Column(String)
    default_on = Column(Boolean)
    servers = relationship("Server", secondary=server_bot_functions, back_populates="bot_functions")
