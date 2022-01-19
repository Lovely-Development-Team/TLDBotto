from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

from . import enablement
from . import user

Base = declarative_base()
engine = create_engine("sqlite:///:memory:", echo=True)

User = user.User
Enablement = enablement.Enablement
