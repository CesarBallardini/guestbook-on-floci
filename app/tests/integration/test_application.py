"""Integration tests for application.py, the composition root: the real pieces fit together.

Importing it connects to nothing: the database engine and the S3 client open their connections
at first use. So the wiring can be checked with addresses where nothing listens.

Starting it (`with TestClient(...)`) checks the database's schema: those tests start it on a
database of their own, or on none that can be reached.
"""

import importlib
import sys
from typing import TYPE_CHECKING

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import clear_mappers

from guestbook.domain.message import Message
from guestbook.infrastructure.database.schema_version import SchemaBehindError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

    from alembic.config import Config

pytestmark = pytest.mark.integration


@pytest.fixture
def application_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    monkeypatch.setenv('DATABASE_URL', 'postgresql://nobody:nothing@127.0.0.1:1/guestbook')
    monkeypatch.setenv('PICTURE_BUCKET', 'a-bucket')
    monkeypatch.setenv('S3_ENDPOINT_URL', 'http://s3.invalid:4566')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'test')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'test')
    sys.modules.pop('application', None)
    yield importlib.import_module('application')
    sys.modules.pop('application', None)
    # Putting the app together maps the domain's Message onto its table, for the whole process.
    # Undone here, so the tests that follow get the plain class whatever order they run in.
    clear_mappers()


def test_the_app_is_put_together_without_connecting_to_anything(application_module: ModuleType) -> None:
    assert isinstance(application_module.application, FastAPI)


def test_the_app_answers_what_needs_no_storage(application_module: ModuleType) -> None:
    client = TestClient(application_module.application)

    assert client.get('/health').text == 'ok\n'
    assert client.get('/static/htmx.min.js').status_code == 200
    # Not the shape of a key: answered before any storage is asked.
    assert client.get('/pictures/not-a-key').status_code == 404


@pytest.mark.parametrize('missing', ['DATABASE_URL', 'PICTURE_BUCKET'])
def test_the_app_does_not_start_without_a_required_setting(
    application_module: ModuleType, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.delenv(missing)

    with pytest.raises(KeyError, match=missing):
        importlib.reload(application_module)


def test_the_domain_class_is_mapped_while_the_app_is_put_together_and_plain_afterwards(
    request: pytest.FixtureRequest,
) -> None:
    assert inspect(Message, raiseerr=False) is None

    request.getfixturevalue('application_module')

    assert inspect(Message, raiseerr=False) is not None


def test_the_app_does_not_start_on_a_database_its_migrations_have_not_reached(
    application_module: ModuleType, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    monkeypatch.setenv('DATABASE_URL', database_url)
    importlib.reload(application_module)

    with pytest.raises(SchemaBehindError), TestClient(application_module.application):
        pass


def test_the_app_starts_on_a_database_with_every_migration(
    application_module: ModuleType, monkeypatch: pytest.MonkeyPatch, database_url: str, alembic_config: Config
) -> None:
    command.upgrade(alembic_config, 'head')
    monkeypatch.setenv('DATABASE_URL', database_url)
    importlib.reload(application_module)

    with TestClient(application_module.application) as client:
        assert client.get('/health').status_code == 200


def test_the_app_starts_when_the_database_cannot_be_reached(application_module: ModuleType) -> None:
    with TestClient(application_module.application) as client:
        assert client.get('/health').status_code == 200
