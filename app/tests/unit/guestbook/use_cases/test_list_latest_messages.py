"""Unit tests for the use case "a visitor reads the guestbook"."""

import pytest

from guestbook.domain.message import Message
from guestbook.use_cases.list_latest_messages import SHOWN_MESSAGES, ListLatestMessagesUseCase
from tests.fakes import FIRST_DATETIME_UTC, InMemoryMessageRepository

pytestmark = pytest.mark.unit


def test_listing_gives_the_newest_messages_up_to_what_the_guestbook_shows(
    message_repository: InMemoryMessageRepository,
) -> None:
    for number in range(5):
        message_repository.add(Message('Ada', f'Message {number}', FIRST_DATETIME_UTC, None))

    messages = ListLatestMessagesUseCase(message_repository, shown_messages=2).list_latest_messages()

    assert [message.body for message in messages] == ['Message 4', 'Message 3']


def test_the_guestbook_shows_fifty_messages_unless_told_otherwise(
    message_repository: InMemoryMessageRepository,
) -> None:
    for number in range(SHOWN_MESSAGES + 1):
        message_repository.add(Message('Ada', f'Message {number}', FIRST_DATETIME_UTC, None))

    assert len(ListLatestMessagesUseCase(message_repository).list_latest_messages()) == SHOWN_MESSAGES
