"""Integration tests: the message repository and the migrations, against the emulator's PostgreSQL.

Each test gets a new database, brought up to date by Alembic as a deploy does.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

import psycopg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, text

from guestbook.domain.errors import StorageError
from guestbook.domain.message import MAX_AUTHOR_LENGTH, MAX_BODY_LENGTH, Message
from guestbook.infrastructure.database.engine import (
    CONNECT_TIMEOUT_SECONDS,
    create_database_engine,
    create_session_factory,
)
from guestbook.infrastructure.database.orm_mapping import metadata
from guestbook.infrastructure.database.sqlalchemy_message_repository import SqlAlchemyMessageRepository
from tests.contracts import MessageRepositoryContractMixin

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

POSTED_DATETIME_UTC = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
WRITERS = 8
MESSAGES_PER_WRITER = 10


@pytest.fixture
def engine(database_url: str, alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, 'head')
    engine = create_database_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def repository(engine: Engine) -> SqlAlchemyMessageRepository:
    return SqlAlchemyMessageRepository(create_session_factory(engine))


class TestSqlAlchemyMessageRepository(MessageRepositoryContractMixin):
    """The repository does everything the in-memory fake does."""

    @pytest.fixture
    def contract_repository(self, repository: SqlAlchemyMessageRepository) -> SqlAlchemyMessageRepository:
        return repository


def test_the_time_comes_back_in_utc_whatever_zone_it_was_given_in(repository: SqlAlchemyMessageRepository) -> None:
    posted_datetime_aware = POSTED_DATETIME_UTC.astimezone(timezone(timedelta(hours=-3)))

    repository.add(Message('Ada', 'Hello', posted_datetime_aware, None))

    (message,) = repository.latest(1)
    assert message.posted_datetime_utc == POSTED_DATETIME_UTC
    assert message.posted_datetime_utc.tzinfo is UTC


def test_a_time_without_a_zone_is_refused(repository: SqlAlchemyMessageRepository) -> None:
    posted_datetime_naive = POSTED_DATETIME_UTC.replace(tzinfo=None)

    with pytest.raises(StorageError):
        repository.add(Message('Ada', 'Hello', posted_datetime_naive, None))


def test_a_message_can_still_be_read_after_it_was_stored_and_after_it_was_loaded(
    repository: SqlAlchemyMessageRepository,
) -> None:
    message = Message('Ada', 'Hello', POSTED_DATETIME_UTC, None)

    repository.add(message)
    (loaded,) = repository.latest(1)

    assert (message.author, message.body) == ('Ada', 'Hello')
    assert (loaded.author, loaded.body, loaded.posted_datetime_utc) == ('Ada', 'Hello', POSTED_DATETIME_UTC)


def test_visitors_who_sign_at_the_same_time_all_get_their_messages_stored_in_their_own_order(
    repository: SqlAlchemyMessageRepository,
) -> None:
    def sign_several(writer: int) -> None:
        for number in range(MESSAGES_PER_WRITER):
            repository.add(Message(f'Writer {writer}', f'{number}', POSTED_DATETIME_UTC, None))

    with ThreadPoolExecutor(max_workers=WRITERS) as executor:
        # list(): wait for every writer, and raise here what one of them raised.
        list(executor.map(sign_several, range(WRITERS)))

    messages = repository.latest(WRITERS * MESSAGES_PER_WRITER + 1)
    assert len(messages) == WRITERS * MESSAGES_PER_WRITER
    for writer in range(WRITERS):
        newest_first = [int(message.body) for message in messages if message.author == f'Writer {writer}']
        assert newest_first == list(range(MESSAGES_PER_WRITER))[::-1]


def test_a_database_that_fails_is_reported_as_a_storage_error(
    repository: SqlAlchemyMessageRepository, engine: Engine
) -> None:
    with engine.begin() as connection:
        connection.execute(text('drop table message'))

    with pytest.raises(StorageError):
        repository.latest(1)
    with pytest.raises(StorageError):
        repository.add(Message('Ada', 'Hello', POSTED_DATETIME_UTC, None))


def test_connections_the_database_closed_are_replaced_without_failing_a_request(
    repository: SqlAlchemyMessageRepository, database_url: str
) -> None:
    repository.add(Message('Ada', 'Hello', POSTED_DATETIME_UTC, None))
    # What a restart of the database does to the connections the pool keeps.
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(
            'select pg_terminate_backend(pid) from pg_stat_activity'
            ' where datname = current_database() and pid <> pg_backend_pid()'
        )

    assert len(repository.latest(10)) == 1


def test_a_database_that_cannot_be_reached_is_reported_without_a_long_wait() -> None:
    # Nothing listens on port 1.
    engine = create_database_engine('postgresql://nobody:nothing@127.0.0.1:1/guestbook')
    nowhere = SqlAlchemyMessageRepository(create_session_factory(engine))
    start_seconds = time.monotonic()

    with pytest.raises(StorageError):
        nowhere.latest(1)

    # Twice the limit: the driver may try more than one address.
    assert time.monotonic() - start_seconds < 2 * CONNECT_TIMEOUT_SECONDS + 1


@pytest.mark.parametrize(
    ('author', 'body'),
    [
        ('', 'Hello'),
        ('Ada', ''),
        ('A' * (MAX_AUTHOR_LENGTH + 1), 'Hello'),
        ('Ada', 'H' * (MAX_BODY_LENGTH + 1)),
    ],
)
def test_the_table_refuses_a_message_that_did_not_go_through_the_rules(
    repository: SqlAlchemyMessageRepository, author: str, body: str
) -> None:
    with pytest.raises(StorageError):
        repository.add(Message(author, body, POSTED_DATETIME_UTC, None))

    assert repository.latest(10) == []


def test_the_table_accepts_texts_as_long_as_the_rules_allow(repository: SqlAlchemyMessageRepository) -> None:
    repository.add(Message('A' * MAX_AUTHOR_LENGTH, 'H' * MAX_BODY_LENGTH, POSTED_DATETIME_UTC, None))

    assert len(repository.latest(10)) == 1


def test_the_limits_in_the_table_are_the_ones_the_rules_have(engine: Engine) -> None:
    # The migrations write the numbers out; the comparison below does not look at checks.
    with engine.connect() as connection:
        checks = dict(
            connection.execute(
                text(
                    'select conname, pg_get_constraintdef(oid) from pg_constraint'
                    " where conrelid = 'message'::regclass and contype = 'c'"
                )
            ).all()
        )

    assert f'<= {MAX_AUTHOR_LENGTH})' in checks['message_author_length']
    assert f'<= {MAX_BODY_LENGTH})' in checks['message_body_length']


def test_the_migrations_make_exactly_the_tables_the_orm_mapping_describes(engine: Engine) -> None:
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), metadata)

    assert differences == []


def test_migrating_again_changes_nothing_and_keeps_the_messages(
    repository: SqlAlchemyMessageRepository, alembic_config: Config
) -> None:
    repository.add(Message('Ada', 'Hello', POSTED_DATETIME_UTC, None))

    command.upgrade(alembic_config, 'head')

    assert len(repository.latest(10)) == 1


def test_the_migrations_can_be_undone(engine: Engine, alembic_config: Config) -> None:
    command.downgrade(alembic_config, 'base')

    with engine.connect() as connection:
        tables = connection.execute(text("select tablename from pg_tables where schemaname = 'public'")).scalars()
        assert set(tables) == {'alembic_version'}
