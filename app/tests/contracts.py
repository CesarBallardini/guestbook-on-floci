"""What every implementation of an output port must do, the in-memory fakes included.

Each mixin is a set of tests written against a port. A test class inherits it and provides the
implementation as a fixture: the unit tests give the fake, the integration tests give the real
adapter. So the fakes the unit tests rely on are held to the same behaviour as what they stand
for.

A class that inherits a mixin defines one fixture, named as the mixin says.
"""

from datetime import UTC, datetime
from typing import Protocol

import pytest

from guestbook.domain.message import Message
from guestbook.domain.output_ports import (
    MessageReaderPort,
    MessageWriterPort,
    PictureReaderPort,
    PictureWriterPort,
)
from guestbook.domain.picture import PICTURE_FORMATS, Picture, PictureFormat
from tests.samples import PNG_FORMAT

POSTED_DATETIME_UTC = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


class MessageRepositoryProtocol(MessageWriterPort, MessageReaderPort, Protocol):
    """Something that both keeps and finds messages."""


class PictureStorageProtocol(PictureWriterPort, PictureReaderPort, Protocol):
    """Something that both keeps and finds pictures."""


class MessageRepositoryContractMixin:
    """Tests for MessageWriterPort and MessageReaderPort. Fixture to define: `contract_repository`, empty."""

    def test_nothing_was_kept_yet(self, contract_repository: MessageRepositoryProtocol) -> None:
        assert contract_repository.latest(10) == []

    def test_a_kept_message_is_found_as_it_was(self, contract_repository: MessageRepositoryProtocol) -> None:
        contract_repository.add(Message('Ada', 'Hello', POSTED_DATETIME_UTC, 'a-key.png'))

        (found,) = contract_repository.latest(10)

        assert found == Message('Ada', 'Hello', POSTED_DATETIME_UTC, 'a-key.png')
        assert found.posted_datetime_utc.utcoffset() == UTC.utcoffset(None)

    def test_a_message_without_picture_has_no_key(self, contract_repository: MessageRepositoryProtocol) -> None:
        contract_repository.add(Message('Ada', 'Hello', POSTED_DATETIME_UTC, None))

        assert contract_repository.latest(1)[0].picture_key is None

    def test_messages_are_found_newest_first_up_to_the_limit(
        self, contract_repository: MessageRepositoryProtocol
    ) -> None:
        for number in range(5):
            contract_repository.add(Message('Ada', f'Message {number}', POSTED_DATETIME_UTC, None))

        found = contract_repository.latest(3)

        assert [message.body for message in found] == ['Message 4', 'Message 3', 'Message 2']

    def test_a_limit_of_zero_finds_nothing(self, contract_repository: MessageRepositoryProtocol) -> None:
        contract_repository.add(Message('Ada', 'Hello', POSTED_DATETIME_UTC, None))

        assert contract_repository.latest(0) == []

    def test_two_messages_with_the_same_content_are_both_kept(
        self, contract_repository: MessageRepositoryProtocol
    ) -> None:
        contract_repository.add(Message('Ada', 'Hello', POSTED_DATETIME_UTC, None))
        contract_repository.add(Message('Ada', 'Hello', POSTED_DATETIME_UTC, None))

        assert len(contract_repository.latest(10)) == 2

    def test_texts_are_kept_exactly_whatever_they_contain(
        self, contract_repository: MessageRepositoryProtocol
    ) -> None:
        text = "'); drop table message; -- <b>ñandú</b> 🙂\nsecond line"

        contract_repository.add(Message(text, text, POSTED_DATETIME_UTC, None))

        (found,) = contract_repository.latest(1)
        assert (found.author, found.body) == (text, text)


class PictureStorageContractMixin:
    """Tests for PictureWriterPort and PictureReaderPort. Fixture to define: `contract_storage`, empty."""

    def test_a_key_nobody_used_has_no_picture(self, contract_storage: PictureStorageProtocol) -> None:
        assert contract_storage.load('missing.png') is None

    @pytest.mark.parametrize('picture_format', PICTURE_FORMATS, ids=[f.name for f in PICTURE_FORMATS])
    def test_a_kept_picture_is_found_with_its_content_and_type(
        self, contract_storage: PictureStorageProtocol, picture_format: PictureFormat
    ) -> None:
        picture = Picture(bytes(range(256)), picture_format)
        picture_key = f'a-key.{picture_format.extension}'

        contract_storage.save(picture_key, picture)

        assert contract_storage.load(picture_key) == picture

    def test_keeping_under_a_used_key_replaces_the_picture(self, contract_storage: PictureStorageProtocol) -> None:
        contract_storage.save('a-key.png', Picture(b'first', PNG_FORMAT))

        contract_storage.save('a-key.png', Picture(b'second', PNG_FORMAT))

        assert contract_storage.load('a-key.png') == Picture(b'second', PNG_FORMAT)

    def test_a_removed_picture_is_not_found_and_the_others_stay(
        self, contract_storage: PictureStorageProtocol
    ) -> None:
        contract_storage.save('one.png', Picture(b'one', PNG_FORMAT))
        contract_storage.save('two.png', Picture(b'two', PNG_FORMAT))

        contract_storage.delete('one.png')

        assert contract_storage.load('one.png') is None
        assert contract_storage.load('two.png') == Picture(b'two', PNG_FORMAT)

    def test_removing_what_is_not_there_is_not_an_error(self, contract_storage: PictureStorageProtocol) -> None:
        contract_storage.delete('missing.png')

        assert contract_storage.load('missing.png') is None

    def test_pictures_under_different_keys_are_kept_apart(self, contract_storage: PictureStorageProtocol) -> None:
        contract_storage.save('one.png', Picture(b'one', PNG_FORMAT))
        contract_storage.save('two.png', Picture(b'two', PNG_FORMAT))

        assert contract_storage.load('one.png') == Picture(b'one', PNG_FORMAT)
        assert contract_storage.load('two.png') == Picture(b'two', PNG_FORMAT)
