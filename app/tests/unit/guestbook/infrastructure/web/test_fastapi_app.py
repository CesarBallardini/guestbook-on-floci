"""Unit tests for the web adapter, on the in-memory fakes."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from guestbook.domain.message import MAX_AUTHOR_LENGTH, MAX_BODY_LENGTH
from guestbook.domain.picture import MAX_PICTURE_BYTES, MAX_PICTURE_MEGABYTES, PICTURE_FORMATS, accepted_format_names
from guestbook.infrastructure.web.fastapi_app import create_fastapi_app
from guestbook.use_cases.get_picture import GetPictureUseCase
from guestbook.use_cases.list_latest_messages import ListLatestMessagesUseCase
from guestbook.use_cases.sign_guestbook import SignGuestbookUseCase
from tests.conftest import VISITOR_BASE_URL
from tests.fakes import InMemoryMessageRepository, InMemoryPictureStorageAdapter

pytestmark = pytest.mark.unit

HTMX = {'HX-Request': 'true'}


def test_an_empty_guestbook_says_so(client: TestClient) -> None:
    answer = client.get('/')

    assert answer.status_code == 200
    assert 'No messages yet.' in answer.text
    assert '/static/htmx.min.js' in answer.text


def test_the_page_brings_its_own_copy_of_htmx(client: TestClient) -> None:
    answer = client.get('/static/htmx.min.js')

    assert answer.status_code == 200
    assert 'htmx' in answer.text


def test_a_post_from_htmx_gets_the_list_of_messages_only(client: TestClient) -> None:
    answer = client.post('/messages', data={'author': 'Ada', 'body': 'Hello'}, headers=HTMX)

    assert answer.status_code == 200
    assert answer.text.lstrip().startswith('<ul id="messages">')
    assert 'Hello' in answer.text
    assert '<html' not in answer.text


def test_a_post_without_javascript_goes_back_to_the_page(client: TestClient) -> None:
    answer = client.post('/messages', data={'author': 'Ada', 'body': 'Hello'})

    assert answer.status_code == 303
    assert answer.headers['Location'] == '/'


def test_a_message_shows_the_time_it_was_posted(client: TestClient) -> None:
    answer = client.post('/messages', data={'author': 'Ada', 'body': 'Hello'}, headers=HTMX)

    assert 'Ada, 2026-06-11 12:00:00 UTC' in answer.text


def test_the_newest_message_comes_first(client: TestClient) -> None:
    client.post('/messages', data={'author': 'Ada', 'body': 'First message'})
    client.post('/messages', data={'author': 'Bob', 'body': 'Second message'})

    page = client.get('/').text

    assert page.index('Second message') < page.index('First message')


def test_what_a_visitor_writes_is_shown_as_text_not_as_html(client: TestClient) -> None:
    answer = client.post('/messages', data={'author': 'Ada', 'body': '<script>alert(1)</script>'}, headers=HTMX)

    assert '<script>' not in answer.text
    assert '&lt;script&gt;' in answer.text


def test_a_message_that_breaks_a_rule_is_refused_and_not_stored(
    client: TestClient, message_repository: InMemoryMessageRepository
) -> None:
    answer = client.post('/messages', data={'author': '', 'body': 'Hello'}, headers=HTMX)

    assert answer.status_code == 400
    assert 'needs a name' in answer.text
    assert message_repository.messages == []


def test_a_picture_is_stored_and_served_back(
    client: TestClient, picture_storage: InMemoryPictureStorageAdapter, png_bytes: bytes
) -> None:
    answer = client.post(
        '/messages',
        data={'author': 'Ada', 'body': 'Look'},
        files={'picture': ('holiday.png', png_bytes)},
        headers=HTMX,
    )

    (key,) = picture_storage.pictures
    assert f'/pictures/{key}' in answer.text
    served = client.get(f'/pictures/{key}')
    assert served.status_code == 200
    assert served.content == png_bytes
    assert served.headers['Content-Type'] == 'image/png'
    assert served.headers['X-Content-Type-Options'] == 'nosniff'


def test_a_form_sent_with_no_file_chosen_is_a_message_without_picture(
    client: TestClient, message_repository: InMemoryMessageRepository
) -> None:
    # What a browser sends when the file field is left empty.
    answer = client.post(
        '/messages', data={'author': 'Ada', 'body': 'Hello'}, files={'picture': ('', b'')}, headers=HTMX
    )

    assert answer.status_code == 200
    assert message_repository.messages[0].picture_key is None


@pytest.mark.parametrize(
    ('content', 'reason'),
    [(b'not an image', 'must be a PNG, JPEG, GIF or WebP image'), (b'\0' * (MAX_PICTURE_BYTES * 2), 'up to 2 MB')],
)
def test_a_refused_picture_stores_nothing(
    client: TestClient,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
    content: bytes,
    reason: str,
) -> None:
    answer = client.post(
        '/messages', data={'author': 'Ada', 'body': 'Look'}, files={'picture': ('holiday.png', content)}, headers=HTMX
    )

    assert answer.status_code == 400
    assert reason in answer.text
    assert message_repository.messages == []
    assert picture_storage.pictures == {}


@pytest.mark.parametrize('key', ['0' * 32 + '.png', 'not-a-key', 'passwd'])
def test_an_unknown_picture_is_not_found(client: TestClient, key: str) -> None:
    assert client.get(f'/pictures/{key}').status_code == 404


def test_health_answers_without_touching_the_stores(client: TestClient) -> None:
    answer = client.get('/health')

    assert (answer.status_code, answer.text) == (200, 'ok\n')


NOT_AVAILABLE = 'The guestbook is not available right now. Please try again later.\n'


def test_messages_that_cannot_be_read_or_stored_are_answered_as_not_available(
    client: TestClient, message_repository: InMemoryMessageRepository
) -> None:
    message_repository.is_available = False

    for answer in (
        client.get('/'),
        client.post('/messages', data={'author': 'Ada', 'body': 'Hello'}),
        client.post('/messages', data={'author': 'Ada', 'body': 'Hello'}, headers=HTMX),
    ):
        # Nothing of the cause is told to the visitor.
        assert (answer.status_code, answer.text) == (503, NOT_AVAILABLE)
    assert client.get('/health').status_code == 200


def test_a_storage_failure_is_logged_with_its_cause(
    client: TestClient, message_repository: InMemoryMessageRepository, caplog: pytest.LogCaptureFixture
) -> None:
    message_repository.is_available = False

    client.get('/')

    (record,) = caplog.records
    assert record.levelname == 'ERROR'
    assert record.getMessage() == 'GET / failed: The messages could not be read.'
    # With the traceback, which leads to what the adapter caught.
    assert record.exc_info is not None


def test_a_picture_that_cannot_be_stored_is_answered_as_not_available_and_leaves_no_message(
    client: TestClient,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
    png_bytes: bytes,
) -> None:
    picture_storage.is_available = False

    answer = client.post(
        '/messages',
        data={'author': 'Ada', 'body': 'Look'},
        files={'picture': ('holiday.png', png_bytes)},
        headers=HTMX,
    )

    assert (answer.status_code, answer.text) == (503, NOT_AVAILABLE)
    assert message_repository.messages == []


def test_a_picture_that_cannot_be_read_is_answered_as_not_available(
    client: TestClient, picture_storage: InMemoryPictureStorageAdapter
) -> None:
    picture_storage.is_available = False

    answer = client.get('/pictures/' + '0' * 32 + '.png')

    assert (answer.status_code, answer.text) == (503, NOT_AVAILABLE)


def test_a_message_without_picture_is_stored_while_the_pictures_cannot_be_reached(
    client: TestClient, message_repository: InMemoryMessageRepository, picture_storage: InMemoryPictureStorageAdapter
) -> None:
    picture_storage.is_available = False

    answer = client.post('/messages', data={'author': 'Ada', 'body': 'Hello'}, headers=HTMX)

    assert answer.status_code == 200
    assert len(message_repository.messages) == 1


def test_a_picture_can_be_kept_by_the_browser_for_good(
    client: TestClient, picture_storage: InMemoryPictureStorageAdapter, png_bytes: bytes
) -> None:
    client.post('/messages', data={'author': 'Ada', 'body': 'Look'}, files={'picture': ('holiday.png', png_bytes)})
    (key,) = picture_storage.pictures

    assert 'immutable' in client.get(f'/pictures/{key}').headers['Cache-Control']


def test_the_form_tells_the_browser_the_limits_of_the_texts(client: TestClient) -> None:
    page = client.get('/').text

    assert f'maxlength="{MAX_AUTHOR_LENGTH}"' in page
    assert f'maxlength="{MAX_BODY_LENGTH}"' in page


def test_the_form_names_the_formats_and_the_limit_the_rules_have(client: TestClient) -> None:
    page = client.get('/').text

    assert f'({accepted_format_names()}, up to {MAX_PICTURE_MEGABYTES} MB)' in page
    for picture_format in PICTURE_FORMATS:
        assert picture_format.content_type in page


def test_the_fields_have_names_for_those_who_cannot_see_the_placeholders(client: TestClient) -> None:
    page = client.get('/').text

    assert 'aria-label="Your name"' in page
    assert 'aria-label="Your message"' in page


def test_a_post_with_no_fields_is_refused_as_a_message_that_breaks_a_rule(client: TestClient) -> None:
    answer = client.post('/messages', headers=HTMX)

    assert answer.status_code == 400
    assert 'needs a name' in answer.text


class StartupRefusedError(Exception):
    pass


def _app_with_startup_checks(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
    startup_checks: list[Callable[[], None]],
) -> FastAPI:
    return create_fastapi_app(
        sign_guestbook_use_case,
        ListLatestMessagesUseCase(message_repository),
        GetPictureUseCase(picture_storage),
        startup_checks=startup_checks,
    )


def test_the_startup_checks_run_in_order_when_the_app_starts_and_not_before(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
) -> None:
    checks_run: list[str] = []
    app = _app_with_startup_checks(
        sign_guestbook_use_case,
        message_repository,
        picture_storage,
        [lambda: checks_run.append('first'), lambda: checks_run.append('second')],
    )
    assert checks_run == []

    with TestClient(app, base_url=VISITOR_BASE_URL) as client:
        assert checks_run == ['first', 'second']
        assert client.get('/health').status_code == 200


def test_a_startup_check_that_raises_stops_the_start(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
) -> None:
    def refuse() -> None:
        raise StartupRefusedError

    app = _app_with_startup_checks(sign_guestbook_use_case, message_repository, picture_storage, [refuse])

    with pytest.raises(StartupRefusedError), TestClient(app, base_url=VISITOR_BASE_URL):
        pass
