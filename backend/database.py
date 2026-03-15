from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import instellingen

motor = create_engine(
    instellingen.database_url,
    pool_pre_ping=True,  # herverbinding bij weggevallen connectie
)

SessieKlasse = sessionmaker(autocommit=False, autoflush=False, bind=motor)


class Basis(DeclarativeBase):
    pass
