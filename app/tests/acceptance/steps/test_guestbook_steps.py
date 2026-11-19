"""Step definitions for guestbook.feature: a visitor's browser, played by FastAPI's test client."""

import re

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from pytest_bdd import given, parsers, scenarios, then, when

from tests.fakes import InMemoryMessageRepository, InMemoryPictureStorageAdapter

scenarios('../features/guestbook.feature')


@pytest.fixture
def last_answer() -> dict[str, Response]:
    return {}


def sign(client: TestClient, last_answer: dict[str, Response], author: str, body: str, picture: bytes) -> None:
    last_answer['signing'] = client.post(
        '/messages',
        data={'author': author, 'body': body},
        files={'picture': ('picture', picture)} if picture else None,
        headers={'HX-Request': 'true'},
    )


@given('an empty guestbook')
def empty_guestbook(message_repository: InMemoryMessageRepository) -> None:
    assert message_repository.messages == []


@given('a guestbook whose messages cannot be reached')
def messages_cannot_be_reached(message_repository: InMemoryMessageRepository) -> None:
    message_repository.is_available = False


@given('a guestbook whose pictures cannot be reached')
def pictures_cannot_be_reached(picture_storage: InMemoryPictureStorageAdapter) -> None:
    picture_storage.is_available = False


@given(parsers.parse('{count:d} visitors signed, one after the other'))
def visitors_signed(client: TestClient, last_answer: dict[str, Response], count: int) -> None:
    for number in range(1, count + 1):
        # The full stop tells "visitor 1." apart from "visitor 10".
        sign(client, last_answer, f'Visitor {number}', f'Greetings from visitor {number}.', b'')
        assert last_answer['signing'].status_code == 200


@when(parsers.parse('"{author}" signs with a message of {length:d} characters'))
def signs_with_long_message(client: TestClient, last_answer: dict[str, Response], author: str, length: int) -> None:
    sign(client, last_answer, author, 'x' * length, b'')


THREE_MEGABYTES = 3 * 1024 * 1024


@when(parsers.re(r'"(?P<author>[^"]*)" signs with the message "(?P<body>[^"]*)" and a picture of 3 MB$'))
def signs_with_big_picture(
    client: TestClient, last_answer: dict[str, Response], author: str, body: str, png_bytes: bytes
) -> None:
    sign(client, last_answer, author, body, png_bytes.ljust(THREE_MEGABYTES, b'\0'))


@when('I open the guestbook')
def open_guestbook(client: TestClient) -> None:
    assert client.get('/').status_code == 200


@given(parsers.re(r'"(?P<author>[^"]*)" signs with the message "(?P<body>[^"]*)"$'))
@when(parsers.re(r'"(?P<author>[^"]*)" signs with the message "(?P<body>[^"]*)"$'))
def signs(client: TestClient, last_answer: dict[str, Response], author: str, body: str) -> None:
    sign(client, last_answer, author, body, b'')


@when(parsers.re(r'"(?P<author>[^"]*)" signs with the message "(?P<body>[^"]*)" and a picture$'))
def signs_with_picture(
    client: TestClient, last_answer: dict[str, Response], author: str, body: str, png_bytes: bytes
) -> None:
    sign(client, last_answer, author, body, png_bytes)


@when(parsers.re(r'"(?P<author>[^"]*)" signs with the message "(?P<body>[^"]*)" and a text file as picture$'))
def signs_with_text_file(client: TestClient, last_answer: dict[str, Response], author: str, body: str) -> None:
    sign(client, last_answer, author, body, b'Just some notes, not an image.')


@then('I see that there are no messages yet')
def no_messages_yet(client: TestClient) -> None:
    assert 'No messages yet.' in client.get('/').text


@then(parsers.parse('the guestbook shows "{body}" by "{author}"'))
def guestbook_shows(client: TestClient, body: str, author: str) -> None:
    page = client.get('/').text
    assert body in page
    assert f'{author}, ' in page


@then(parsers.parse('"{first}" is shown before "{second}"'))
def shown_before(client: TestClient, first: str, second: str) -> None:
    page = client.get('/').text
    assert page.index(first) < page.index(second)


@then('the message has a picture that can be downloaded')
def picture_can_be_downloaded(client: TestClient, png_bytes: bytes) -> None:
    source = re.search(r'<img src="([^"]+)"', client.get('/').text)
    assert source is not None
    assert client.get(source.group(1)).content == png_bytes


@then(parsers.parse('the message is refused because "{reason}"'))
def message_refused(last_answer: dict[str, Response], reason: str) -> None:
    assert last_answer['signing'].status_code == 400
    assert reason in last_answer['signing'].text


@then(parsers.re(r'the guestbook shows (?P<count>\d+) messages?$'))
def guestbook_shows_count(client: TestClient, count: str) -> None:
    assert client.get('/').text.count('<li>') == int(count)


@then(parsers.parse('the guestbook does not show "{text}"'))
def guestbook_does_not_show(client: TestClient, text: str) -> None:
    assert text not in client.get('/').text


@then('the page has no script written by a visitor')
def no_script_from_a_visitor(client: TestClient) -> None:
    page = client.get('/').text
    # The one script of the page is its own copy of HTMX.
    assert page.count('<script') == 1
    assert '&lt;script&gt;' in page


@then('I am told that the guestbook is not available right now')
def told_not_available(client: TestClient, last_answer: dict[str, Response]) -> None:
    assert last_answer['signing'].status_code == 503
    assert 'not available right now' in last_answer['signing'].text
    assert client.get('/').status_code == 503
