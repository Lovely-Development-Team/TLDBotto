from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from botto.models import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    airtable_id = Column(String)
    discord_id = Column(String)
    name = Column(String)
    timezone = relationship("Timezone", back_populates="users")