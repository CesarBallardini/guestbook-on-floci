"""Unit tests for the rules for messages."""

import pytest

from guestbook.domain.errors import InvalidMessageError
from guestbook.domain.message import MAX_AUTHOR_LENGTH, MAX_BODY_LENGTH, new_message
from guestbook.domain.picture import Picture
from tests.samples import PNG_FORMAT

pytestmark = pytest.mark.unit


def test_a_message_keeps_its_texts_without_the_spaces_around() -> None:
    message = new_message('  Ada ', '\nHello\n')

    assert (message.author, message.body, message.picture) == ('Ada', 'Hello', None)


@pytest.mark.parametrize(
    ('author', 'body'),
    [
        ('', 'Hello'),
        ('   ', 'Hello'),
        ('Ada', ''),
        ('Ada', ' \n '),
        ('A' * (MAX_AUTHOR_LENGTH + 1), 'Hello'),
        ('Ada', 'H' * (MAX_BODY_LENGTH + 1)),
    ],
)
def test_an_empty_or_too_long_text_is_refused(author: str, body: str) -> None:
    with pytest.raises(InvalidMessageError):
        new_message(author, body)


@pytest.mark.parametrize(('author', 'body'), [('A\x00da', 'Hello'), ('Ada', 'Hel\x00lo')])
def test_a_text_with_the_nul_character_is_refused(author: str, body: str) -> None:
    with pytest.raises(InvalidMessageError, match='NUL character'):
        new_message(author, body)


def test_texts_of_exactly_the_maximum_length_are_accepted() -> None:
    message = new_message('A' * MAX_AUTHOR_LENGTH, 'H' * MAX_BODY_LENGTH)

    assert len(message.author) == MAX_AUTHOR_LENGTH
    assert len(message.body) == MAX_BODY_LENGTH


def test_a_message_with_a_picture_carries_it_checked(png_bytes: bytes) -> None:
    assert new_message('Ada', 'Hello', png_bytes).picture == Picture(png_bytes, PNG_FORMAT)


def test_a_message_with_a_refused_picture_is_refused() -> None:
    with pytest.raises(InvalidMessageError, match='PNG, JPEG, GIF or WebP'):
        new_message('Ada', 'Hello', b'<script>alert(1)</script>')
