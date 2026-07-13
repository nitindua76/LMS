"""
First test suite in this repo — there was no pytest setup before session
scheduling needed one. These are integration tests against the real Postgres
from docker-compose (`docker compose up -d db`), not sqlite-mocked unit
tests, since the schema relies on Postgres-only features (JSONB, native
enums, the num_nonnulls() check constraint on session_audience_rules).

Each test runs inside an outer transaction plus a SAVEPOINT that's restarted
every time application code calls session.commit() (the routers/services
under test commit directly, not just flush) — see the classic SQLAlchemy
"join a session into an external transaction" recipe. The whole outer
transaction is rolled back at teardown, so tests never leave rows behind.
"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    trans = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    trans.rollback()
    connection.close()
