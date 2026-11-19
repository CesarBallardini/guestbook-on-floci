"""Shared fixtures: the guestbook, put together as application.py does, on the in-memory fakes."""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from guestbook.infrastructure.web.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, new_csrf_token
from guestbook.infrastructure.web.fastapi_app import create_fastapi_app
from guestbook.use_cases.get_picture import GetPictureUseCase
from guestbook.use_cases.list_latest_messages import ListLatestMessagesUseCase
from guestbook.use_cases.sign_guestbook import SignGuestbookUseCase
from tests.fakes import (
    FixedClockAdapter,
    InMemoryMessageRepository,
    InMemoryPictureStorageAdapter,
    SequenceUuidGeneratorAdapter,
)

# A real image, one transparent pixel, so a browser can show it.
PNG_BYTES = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)


@pytest.fixture
def png_bytes() -> bytes:
    return PNG_BYTES


@pytest.fixture
def message_repository() -> InMemoryMessageRepository:
    return InMemoryMessageRepository()


@pytest.fixture
def picture_storage() -> InMemoryPictureStorageAdapter:
    return InMemoryPictureStorageAdapter()


@pytest.fixture
def clock() -> FixedClockAdapter:
    return FixedClockAdapter()


@pytest.fixture
def uuid_generator() -> SequenceUuidGeneratorAdapter:
    return SequenceUuidGeneratorAdapter()


@pytest.fixture
def sign_guestbook_use_case(
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
    clock: FixedClockAdapter,
    uuid_generator: SequenceUuidGeneratorAdapter,
) -> SignGuestbookUseCase:
    return SignGuestbookUseCase(message_repository, picture_storage, clock, uuid_generator)


@pytest.fixture
def app(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
) -> FastAPI:
    return create_fastapi_app(
        sign_guestbook_use_case, ListLatestMessagesUseCase(message_repository), GetPictureUseCase(picture_storage)
    )


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """A visitor who has the page open: their posts carry the token the page gave them.

    The token goes as a header, which the app accepts like the form's field, so that each test
    writes only the fields it is about. The browser already has its cookie, as after an earlier
    visit, so this does not depend on the page being available now. `new_visitor` is one who
    never opened the page; tests/unit/.../web/test_csrf.py follows the token from the page itself.
    """
    client = TestClient(app, follow_redirects=False)
    csrf_token = new_csrf_token()
    client.cookies.set(CSRF_COOKIE_NAME, csrf_token)
    client.headers[CSRF_HEADER_NAME] = csrf_token
    return client


@pytest.fixture
def new_visitor(app: FastAPI) -> TestClient:
    return TestClient(app, follow_redirects=False)
