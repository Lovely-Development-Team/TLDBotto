from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String
from botto.models import Base


class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    airtable_id = Column(String)
    discord_id = Column(String)
    name = Column(String)
