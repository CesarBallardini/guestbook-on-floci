"""Where the integration tests find the emulator, and the throwaway databases they work in.

They need the emulator running and `terraform apply` done (the RDS instance must exist). Each
test works in a database or a bucket of its own, made for it and removed afterwards, so the
guestbook's own data is never touched.

The defaults are the emulator's addresses as this machine sees them. To point the tests
elsewhere, set GUESTBOOK_TEST_POSTGRES_URL (a URL of the `postgres` database, with a user that
may create databases) and GUESTBOOK_TEST_S3_ENDPOINT_URL.
"""

import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import psycopg
import pytest
from alembic.config import Config
from psycopg import sql

if TYPE_CHECKING:
    from collections.abc import Iterator

# The app's folder, where alembic.ini is.
APP_DIR = Path(__file__).parents[2]

POSTGRES_URL = os.environ.get(
    'GUESTBOOK_TEST_POSTGRES_URL', 'postgresql://postgres:development-only@127.0.0.1:7001/postgres'
)
S3_ENDPOINT_URL = os.environ.get('GUESTBOOK_TEST_S3_ENDPOINT_URL', 'http://127.0.0.1:4566')


@pytest.fixture
def database_url() -> Iterator[str]:
    """A new, empty database: no table, not even Alembic's."""
    database_name = f'guestbook_test_{uuid.uuid4().hex}'
    with psycopg.connect(POSTGRES_URL, autocommit=True) as connection:
        connection.execute(sql.SQL('create database {}').format(sql.Identifier(database_name)))
    yield POSTGRES_URL.rsplit('/', 1)[0] + f'/{database_name}'
    with psycopg.connect(POSTGRES_URL, autocommit=True) as connection:
        connection.execute(sql.SQL('drop database {} with (force)').format(sql.Identifier(database_name)))


@pytest.fixture
def alembic_config(database_url: str) -> Config:
    """Alembic, as the app's alembic.ini sets it up, on that database."""
    config = Config(APP_DIR / 'alembic.ini')
    config.set_main_option('sqlalchemy.url', database_url)
    return config
