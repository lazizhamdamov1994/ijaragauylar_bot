from app.db.base import Base
from app.db import models  # noqa: F401  (modellar Base.metadata'ga ro'yxatdan o'tishi uchun)

__all__ = ["Base", "models"]
