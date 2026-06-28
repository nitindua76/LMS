from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from .config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Run dynamic schema migration to add progress_measure if not exists
try:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE scorm_cmi_data ADD COLUMN IF NOT EXISTS progress_measure FLOAT"))
except Exception:
    pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
