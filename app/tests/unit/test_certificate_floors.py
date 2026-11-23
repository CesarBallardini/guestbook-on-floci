"""Nothing here drops below the releases the eMudhra certificate advisory of 2026-10-20 names.

Eight intermediate CA keys are compromised, and these releases stop trusting them. The
instance's Python comes from the Amazon Linux image in floci/image-catalog.yaml; the playbook
checks it against minimum_python_version, the floor checked here.
"""

import re
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_DIR = Path(__file__).parents[3]
PYTHON_FLOOR = '3.14.10'
DOTTED_VERSION = r'(\d+(?:\.\d+)*)'
type Version = tuple[int, ...]


def version_of(text: str) -> Version:
    return tuple(int(part) for part in text.split('.'))


def locked_version(name: str) -> str:
    lock = tomllib.loads((REPOSITORY_DIR / 'app/uv.lock').read_text(encoding='utf-8'))
    versions: list[str] = [package['version'] for package in lock['package'] if package['name'] == name]
    assert len(versions) == 1, f'{name} locked {len(versions)} times'
    return versions[0]


def only_match(relative_path: str, pattern: str) -> str:
    text = (REPOSITORY_DIR / relative_path).read_text(encoding='utf-8')
    matches: list[str] = re.findall(pattern, text, flags=re.MULTILINE)
    assert len(matches) == 1, f'{relative_path} matches {pattern!r} {len(matches)} times'
    return matches[0]


@pytest.mark.parametrize(('package', 'floor'), [('certifi', '2026.10.19'), ('pip', '26.2.2')])
def test_the_lockfile_stays_at_or_above_the_floor(package: str, floor: str) -> None:
    assert version_of(locked_version(package)) >= version_of(floor)


@pytest.mark.parametrize(
    ('relative_path', 'pattern', 'floor'),
    [
        # A bare `3.14` fails here too, as it should: uv would take any older 3.14 it finds.
        ('app/.python-version', rf'^{DOTTED_VERSION}$', PYTHON_FLOOR),
        ('app/pyproject.toml', rf'^requires-python = ">={DOTTED_VERSION}"$', PYTHON_FLOOR),
        ('ansible/Dockerfile', rf'^FROM python:{DOTTED_VERSION}-slim\b', PYTHON_FLOOR),
        ('ansible/playbook.yml', rf'^ +minimum_python_version: "{DOTTED_VERSION}"$', PYTHON_FLOOR),
        ('ansible/playbook.yml', rf'^ +uv_version: "{DOTTED_VERSION}"$', '0.13.6'),
    ],
)
def test_every_pin_stays_at_or_above_the_floor(relative_path: str, pattern: str, floor: str) -> None:
    assert version_of(only_match(relative_path, pattern)) >= version_of(floor)


def test_the_running_python_rejects_the_compromised_intermediates() -> None:
    assert sys.version_info >= version_of(PYTHON_FLOOR), (
        f'run `uv python install {PYTHON_FLOOR}`, then recreate .venv with `make install`'
    )
