from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

from . import enablement
from . import meal
from . import reminder
from . import server
from . import timezone
from . import user

Base = declarative_base()
engine = create_engine("sqlite:///:memory:", echo=True)

Enablement = enablement.Enablement
Meal = meal.Meal
Reminder = reminder.Reminder
Server = server.Server
TimeZone = timezone.TimeZone
User = user.User
