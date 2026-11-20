"""Unit tests: alembic.ini finds the migrations wherever the guestbook package is.

The same file is read from the app's folder and, shipped in the wheel, from an installed
release. So it names the migrations by package, never by a path.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

import guestbook
import guestbook.infrastructure.database

pytestmark = pytest.mark.unit

ALEMBIC_INI = Path(guestbook.__file__).parents[1] / 'alembic.ini'
MIGRATIONS_DIR = Path(guestbook.infrastructure.database.__file__).parent / 'migrations'


@pytest.fixture
def alembic_config() -> Config:
    return Config(ALEMBIC_INI)


def test_the_migrations_are_named_by_package(alembic_config: Config) -> None:
    assert alembic_config.get_main_option('script_location') == 'guestbook.infrastructure.database:migrations'


def test_the_migrations_are_found_in_the_package(alembic_config: Config) -> None:
    script_directory = ScriptDirectory.from_config(alembic_config)

    assert Path(script_directory.dir).resolve() == MIGRATIONS_DIR.resolve()


def test_every_revision_file_is_a_migration(alembic_config: Config) -> None:
    script_directory = ScriptDirectory.from_config(alembic_config)

    revision_files = {path.name for path in (MIGRATIONS_DIR / 'versions').glob('*.py')}
    found_files = {Path(revision.path).name for revision in script_directory.walk_revisions()}
    assert found_files == revision_files
    assert found_files


def test_the_migrations_end_in_one_head(alembic_config: Config) -> None:
    script_directory = ScriptDirectory.from_config(alembic_config)

    assert len(script_directory.get_heads()) == 1
