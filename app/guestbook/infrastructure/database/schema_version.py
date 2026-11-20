"""Whether the database's schema fits this release: up to date, behind it, or ahead of it.

A release runs on the schema its own migrations make, and on the schema of any later release:
a rollback leaves the newer schema in place, and every migration must still suit the releases
before it (expand and contract, docs/guestbook.md). What a release cannot run on is a schema
its migrations have not reached.

Run as a program, it prints the state's word for the database that DATABASE_URL names, and
exits non-zero when that database cannot be reached. The playbook reads it:

    python -m guestbook.infrastructure.database.schema_version
"""

import enum
import logging
import os
import sys
from typing import TYPE_CHECKING

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.exc import SQLAlchemyError

from guestbook.domain.errors import StorageError
from guestbook.infrastructure.database.engine import create_database_engine

if TYPE_CHECKING:
    from sqlalchemy import Engine

# The same as in alembic.ini, which is found at another path in the app's folder than in an
# installed release. Named here, the migrations are found without it.
MIGRATIONS_LOCATION = 'guestbook.infrastructure.database:migrations'
PATH_SEPARATOR = 'os'

_logger = logging.getLogger(__name__)


class SchemaState(enum.StrEnum):
    """Where the database's schema stands, compared to this release's migrations."""

    UP_TO_DATE = 'up-to-date'
    # No migration has run, or not this release's latest.
    BEHIND = 'behind'
    # A revision this release does not know: a newer release migrated the database.
    AHEAD = 'ahead'


class SchemaBehindError(Exception):
    """The database's schema is older than this release: its migrations have not run."""


def migrations_directory() -> ScriptDirectory:
    """Return this release's migrations, where alembic.ini says they are."""
    config = Config()
    config.set_main_option('script_location', MIGRATIONS_LOCATION)
    config.set_main_option('path_separator', PATH_SEPARATOR)
    return ScriptDirectory.from_config(config)


def read_schema_state(engine: Engine) -> SchemaState:
    """Compare the database's revision with this release's latest migration.

    Raises:
        StorageError: The database could not be read.
    """
    script_directory = migrations_directory()
    try:
        with engine.connect() as connection:
            database_revisions = set(MigrationContext.configure(connection).get_current_heads())
    except SQLAlchemyError as error:
        raise StorageError("The version of the database's schema could not be read.") from error
    if database_revisions == set(script_directory.get_heads()):
        return SchemaState.UP_TO_DATE
    known_revisions = {revision.revision for revision in script_directory.walk_revisions()}
    if database_revisions - known_revisions:
        return SchemaState.AHEAD
    return SchemaState.BEHIND


def check_schema_at_startup(engine: Engine) -> None:
    """Refuse to start on a schema that is behind this release; start on any other.

    A database that cannot be reached does not stop the start: the app answers each request
    that needs it with a page that says so, and serves the others. Refusing would keep the app
    down after the database is back.

    Raises:
        SchemaBehindError: The schema is behind this release.
    """
    try:
        state = read_schema_state(engine)
    except StorageError:
        _logger.warning("The database's schema was not checked: the database cannot be reached.", exc_info=True)
        return
    if state is SchemaState.BEHIND:
        message = (
            "The database's schema is behind this release: its migrations have not run."
            ' Run "alembic upgrade head" from this release, then start it again.'
        )
        _logger.error(message)
        raise SchemaBehindError(message)
    if state is SchemaState.AHEAD:
        _logger.warning("The database's schema is ahead of this release: a newer release migrated it.")


def main() -> int:
    """Print the schema's state for the database DATABASE_URL names; 1 when it cannot be read."""
    engine = create_database_engine(os.environ['DATABASE_URL'])
    try:
        state = read_schema_state(engine)
    except StorageError as error:
        sys.stderr.write(f'{error} {error.__cause__}\n')
        return 1
    finally:
        engine.dispose()
    sys.stdout.write(f'{state}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
