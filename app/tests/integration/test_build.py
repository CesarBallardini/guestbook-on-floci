"""Integration tests for the build: the wheel holds what a release needs, and nothing else.

A release is made from the wheel alone, so a file missing from it is missing on the instance.
Building runs uv and may download the build backend, which is why these tests are here and
not with the unit tests. They need no emulator.
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from tests.integration.conftest import APP_DIR

pytestmark = pytest.mark.integration

PACKAGE_DIR = APP_DIR / 'guestbook'


@pytest.fixture(scope='module')
def wheel_names(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    """The paths inside a wheel built now, from the app's folder."""
    uv = shutil.which('uv')
    assert uv is not None, 'uv is needed to build the app'
    out_dir = tmp_path_factory.mktemp('dist')
    subprocess.run([uv, 'build', '--wheel', '--out-dir', str(out_dir)], cwd=APP_DIR, check=True, capture_output=True)  # noqa: S603
    (wheel,) = out_dir.glob('*.whl')
    with zipfile.ZipFile(wheel) as archive:
        return set(archive.namelist())


def package_files() -> set[str]:
    """Every file of the guestbook package, as a path from the app's folder."""
    return {
        path.relative_to(APP_DIR).as_posix()
        for path in PACKAGE_DIR.rglob('*')
        if path.is_file() and '__pycache__' not in path.parts
    }


def test_the_wheel_holds_every_file_of_the_package(wheel_names: set[str]) -> None:
    assert package_files() - wheel_names == set()


@pytest.mark.parametrize(
    'name',
    [
        'guestbook/infrastructure/web/templates/page.html',
        'guestbook/infrastructure/web/templates/messages.html',
        'guestbook/infrastructure/web/static/htmx.min.js',
        'guestbook/infrastructure/database/migrations/env.py',
        'guestbook/infrastructure/database/migrations/script.py.mako',
    ],
)
def test_the_wheel_holds_what_is_not_python_code(wheel_names: set[str], name: str) -> None:
    assert name in wheel_names


def test_the_wheel_holds_what_gunicorn_and_alembic_are_pointed_at(wheel_names: set[str]) -> None:
    assert 'application.py' in wheel_names
    assert 'guestbook/alembic.ini' in wheel_names


def test_the_wheel_holds_nothing_but_the_app(wheel_names: set[str]) -> None:
    top_level_names = {name.split('/', 1)[0] for name in wheel_names}

    assert {name for name in top_level_names if not name.endswith('.dist-info')} == {'guestbook', 'application.py'}
    assert not any(Path(name).name.startswith(('test_', 'conftest')) for name in wheel_names)
