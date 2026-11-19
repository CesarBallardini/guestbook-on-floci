"""How the guestbook connects to its database."""

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker

# SQLAlchemy's name for PostgreSQL through psycopg 3.
_DRIVER_NAME = 'postgresql+psycopg'
# How long to wait for the database to accept a connection. Without a limit, a visitor waits
# for minutes when the database is down (130 seconds, measured) before being told so. The
# database is on the same network as the app, where a connection takes milliseconds.
CONNECT_TIMEOUT_SECONDS = 5


def create_database_engine(database_url: str) -> Engine:
    """Make the engine for a database, given its URL in the usual `postgresql://` form."""
    return create_engine(
        make_url(database_url).set(drivername=_DRIVER_NAME),
        connect_args={'connect_timeout': CONNECT_TIMEOUT_SECONDS},
        # Try a kept connection before using it: after the database restarts, the ones the pool
        # holds are dead, and each would fail one visitor's request before being replaced.
        pool_pre_ping=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Make what the repositories open their sessions with.

    A domain object keeps its values after the transaction that stored it: the use case that
    made it may still read it, and must not be sent back to the database for that.
    """
    return sessionmaker(engine, expire_on_commit=False)
