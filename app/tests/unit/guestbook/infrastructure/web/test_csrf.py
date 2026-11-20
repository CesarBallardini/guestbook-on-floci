"""Unit tests for the protection against forged posts."""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from guestbook.infrastructure.web.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FIELD_NAME,
    CSRF_HEADER_NAME,
    csrf_tokens_match,
    new_csrf_token,
)
from tests.conftest import VISITOR_BASE_URL
from tests.fakes import InMemoryMessageRepository

pytestmark = pytest.mark.unit

A_MESSAGE = {'author': 'Ada', 'body': 'Hello'}
OUT_OF_DATE = 'This page is out of date. Please load it again, then sign the guestbook.\n'
# 32 random bytes, written as text.
SHORTEST_TOKEN_LENGTH = 43


def token_in_the_form(page: str) -> str:
    found = re.search(rf'name="{CSRF_FIELD_NAME}" value="([^"]+)"', page)
    assert found
    return found.group(1)


def test_tokens_are_long_and_never_the_same() -> None:
    tokens = {new_csrf_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(len(token) >= SHORTEST_TOKEN_LENGTH for token in tokens)


@pytest.mark.parametrize(
    ('cookie_token', 'sent_token', 'expected'),
    [
        ('a-token', 'a-token', True),
        ('a-token', 'another', False),
        ('a-token', None, False),
        ('a-token', '', False),
        (None, 'a-token', False),
        ('', '', False),
        (None, None, False),
        ('ñandú', 'ñandú', True),
    ],
)
def test_tokens_match_only_when_both_are_there_and_the_same(
    cookie_token: str | None, sent_token: str | None, expected: bool
) -> None:
    assert csrf_tokens_match(cookie_token, sent_token) is expected


def test_the_page_gives_the_same_token_in_a_cookie_and_in_the_form(new_visitor: TestClient) -> None:
    answer = new_visitor.get('/')

    assert token_in_the_form(answer.text) == new_visitor.cookies[CSRF_COOKIE_NAME]
    cookie = answer.headers['Set-Cookie'].lower()
    assert 'httponly' in cookie
    assert 'samesite=strict' in cookie


def test_the_cookie_is_sent_over_https_only_and_to_this_host_only(new_visitor: TestClient) -> None:
    # A browser keeps a "__Host-" cookie only when it is Secure, for the path "/" and names no
    # domain; otherwise it drops it, and every post would be refused.
    answer = new_visitor.get('/')

    name, _, attributes = answer.headers['Set-Cookie'].partition('=')
    attribute_names = {part.strip().split('=')[0].lower() for part in attributes.split(';')[1:]}
    assert name == CSRF_COOKIE_NAME
    assert name.startswith('__Host-')
    assert 'secure' in attribute_names
    assert 'path=/' in answer.headers['Set-Cookie'].lower().replace(' ', '')
    assert 'domain' not in attribute_names


def test_over_plain_http_the_cookie_does_not_come_back(app: FastAPI) -> None:
    # What a browser does too: a Secure cookie stays home when the page is plain HTTP. So the
    # guestbook works over HTTPS only, and the load balancer sends plain HTTP there.
    over_plain_http = TestClient(app, base_url='http://testserver')
    token = token_in_the_form(over_plain_http.get('/').text)

    answer = over_plain_http.post('/messages', data={**A_MESSAGE, CSRF_FIELD_NAME: token})

    assert answer.status_code == 403
    assert answer.text == OUT_OF_DATE


def test_two_visitors_get_different_tokens_and_each_keeps_theirs(app: FastAPI, new_visitor: TestClient) -> None:
    first, second = new_visitor, TestClient(app, base_url=VISITOR_BASE_URL)

    first_token = token_in_the_form(first.get('/').text)

    assert token_in_the_form(second.get('/').text) != first_token
    assert token_in_the_form(first.get('/').text) == first_token


def test_a_post_with_the_token_of_the_page_as_a_field_is_accepted(
    new_visitor: TestClient, message_repository: InMemoryMessageRepository
) -> None:
    token = token_in_the_form(new_visitor.get('/').text)

    answer = new_visitor.post('/messages', data={**A_MESSAGE, CSRF_FIELD_NAME: token})

    assert answer.status_code == 303
    assert len(message_repository.messages) == 1


def test_a_post_with_the_token_as_a_header_is_accepted(
    new_visitor: TestClient, message_repository: InMemoryMessageRepository
) -> None:
    token = token_in_the_form(new_visitor.get('/').text)

    answer = new_visitor.post('/messages', data=A_MESSAGE, headers={CSRF_HEADER_NAME: token})

    assert answer.status_code == 303
    assert len(message_repository.messages) == 1


def test_a_post_from_a_browser_that_never_got_the_page_is_refused(
    new_visitor: TestClient, message_repository: InMemoryMessageRepository
) -> None:
    answer = new_visitor.post('/messages', data={**A_MESSAGE, CSRF_FIELD_NAME: 'made-up'})

    assert (answer.status_code, answer.text) == (403, OUT_OF_DATE)
    assert message_repository.messages == []


def test_a_forged_post_which_has_the_cookie_but_cannot_know_the_token_is_refused(
    new_visitor: TestClient, message_repository: InMemoryMessageRepository
) -> None:
    new_visitor.get('/')

    for data in (A_MESSAGE, {**A_MESSAGE, CSRF_FIELD_NAME: 'a-guess'}):
        answer = new_visitor.post('/messages', data=data)

        assert (answer.status_code, answer.text) == (403, OUT_OF_DATE)
    assert message_repository.messages == []


def test_a_refused_post_is_refused_before_its_message_is_looked_at(new_visitor: TestClient) -> None:
    # An empty message would be a 400; the forged post never gets that far.
    assert new_visitor.post('/messages', data={'author': '', 'body': ''}).status_code == 403


def test_reading_needs_no_token(new_visitor: TestClient) -> None:
    assert new_visitor.get('/').status_code == 200
    assert new_visitor.get('/health').status_code == 200
