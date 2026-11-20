"""Integration tests: the schema's state, against the emulator's PostgreSQL.

Each test gets a new, empty database and brings it to the revision it needs, as a deploy or a
rollback would leave it.
"""

import logging
import os
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest
from alembic import command
from sqlalchemy import text

from guestbook.domain.errors import StorageError
from guestbook.infrastructure.database.engine import CONNECT_TIMEOUT_SECONDS, create_database_engine
from guestbook.infrastructure.database.schema_version import (
    SchemaBehindError,
    SchemaState,
    check_schema_at_startup,
    migrations_directory,
    read_schema_state,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from alembic.config import Config
    from sqlalchemy import Engine

pytestmark = pytest.mark.integration

# Nothing listens on port 1.
UNREACHABLE_DATABASE_URL = 'postgresql://nobody:nothing@127.0.0.1:1/guestbook'
# What a newer release's migration leaves in the database: a revision this release does not know.
NEWER_REVISION = 'a_newer_release'


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_database_engine(database_url)
    yield engine
    engine.dispose()


def _upgrade_to_the_revision_before_the_latest(alembic_config: Config) -> None:
    latest = migrations_directory().get_revision('head')
    assert latest is not None
    assert isinstance(latest.down_revision, str), 'needs two migrations, one after the other'
    command.upgrade(alembic_config, latest.down_revision)


def _migrate_as_a_newer_release(alembic_config: Config, engine: Engine) -> None:
    command.upgrade(alembic_config, 'head')
    with engine.begin() as connection:
        connection.execute(text('update alembic_version set version_num = :revision'), {'revision': NEWER_REVISION})


def test_an_empty_database_is_behind(engine: Engine) -> None:
    assert read_schema_state(engine) is SchemaState.BEHIND


def test_a_database_without_the_latest_migration_is_behind(engine: Engine, alembic_config: Config) -> None:
    _upgrade_to_the_revision_before_the_latest(alembic_config)

    assert read_schema_state(engine) is SchemaState.BEHIND


def test_a_database_with_every_migration_is_up_to_date(engine: Engine, alembic_config: Config) -> None:
    command.upgrade(alembic_config, 'head')

    assert read_schema_state(engine) is SchemaState.UP_TO_DATE


def test_a_database_a_newer_release_migrated_is_ahead(engine: Engine, alembic_config: Config) -> None:
    _migrate_as_a_newer_release(alembic_config, engine)

    assert read_schema_state(engine) is SchemaState.AHEAD


def test_a_database_that_cannot_be_reached_is_reported_without_a_long_wait() -> None:
    engine = create_database_engine(UNREACHABLE_DATABASE_URL)
    start_seconds = time.monotonic()

    with pytest.raises(StorageError):
        read_schema_state(engine)

    # Twice the limit: the driver may try more than one address.
    assert time.monotonic() - start_seconds < 2 * CONNECT_TIMEOUT_SECONDS + 1


def test_the_start_is_refused_on_a_schema_behind_the_release(engine: Engine, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(SchemaBehindError, match='alembic upgrade head'):
        check_schema_at_startup(engine)

    assert "The database's schema is behind this release" in caplog.text


def test_the_app_starts_quietly_on_a_schema_up_to_date(
    engine: Engine, alembic_config: Config, caplog: pytest.LogCaptureFixture
) -> None:
    command.upgrade(alembic_config, 'head')
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        check_schema_at_startup(engine)

    assert caplog.records == []


def test_the_app_starts_on_a_schema_a_newer_release_migrated_and_says_so(
    engine: Engine, alembic_config: Config, caplog: pytest.LogCaptureFixture
) -> None:
    _migrate_as_a_newer_release(alembic_config, engine)

    check_schema_at_startup(engine)

    assert "The database's schema is ahead of this release" in caplog.text


def test_the_app_starts_when_the_database_cannot_be_reached_and_says_so(caplog: pytest.LogCaptureFixture) -> None:
    engine = create_database_engine(UNREACHABLE_DATABASE_URL)

    check_schema_at_startup(engine)

    assert "The database's schema was not checked" in caplog.text


def _run_as_a_program(database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'guestbook.infrastructure.database.schema_version'],
        env={**os.environ, 'DATABASE_URL': database_url},
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_as_a_program_it_prints_the_state(database_url: str, alembic_config: Config) -> None:
    command.upgrade(alembic_config, 'head')

    finished = _run_as_a_program(database_url)

    assert finished.returncode == 0
    assert finished.stdout == 'up-to-date\n'


def test_run_as_a_program_it_fails_when_the_database_cannot_be_reached() -> None:
    finished = _run_as_a_program(UNREACHABLE_DATABASE_URL)

    assert finished.returncode == 1
    assert finished.stdout == ''
    assert "The version of the database's schema could not be read." in finished.stderr
