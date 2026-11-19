"""Unit tests for tests/fakes.py: the fakes pass the same contracts as the adapters they stand for."""

from datetime import timedelta

import pytest

from guestbook.domain.errors import StorageError
from guestbook.domain.message import Message
from guestbook.domain.picture import Picture
from tests.contracts import MessageRepositoryContractMixin, PictureStorageContractMixin
from tests.fakes import (
    FIRST_DATETIME_UTC,
    FixedClockAdapter,
    InMemoryMessageRepository,
    InMemoryPictureStorageAdapter,
    SequenceUuidGeneratorAdapter,
)
from tests.samples import PNG_FORMAT

pytestmark = pytest.mark.unit


class TestInMemoryMessageRepository(MessageRepositoryContractMixin):
    @pytest.fixture
    def contract_repository(self) -> InMemoryMessageRepository:
        return InMemoryMessageRepository()


class TestInMemoryPictureStorageAdapter(PictureStorageContractMixin):
    @pytest.fixture
    def contract_storage(self) -> InMemoryPictureStorageAdapter:
        return InMemoryPictureStorageAdapter()


def test_a_repository_made_unavailable_fails_as_a_storage_does() -> None:
    repository = InMemoryMessageRepository()
    repository.is_available = False

    with pytest.raises(StorageError):
        repository.add(Message('Ada', 'Hello', FIRST_DATETIME_UTC, None))
    with pytest.raises(StorageError):
        repository.latest(1)


def test_a_picture_storage_made_unavailable_fails_as_a_storage_does() -> None:
    storage = InMemoryPictureStorageAdapter()
    storage.is_available = False

    with pytest.raises(StorageError):
        storage.save('a-key.png', Picture(b'...', PNG_FORMAT))
    with pytest.raises(StorageError):
        storage.load('a-key.png')


def test_the_fixed_clock_shows_the_same_time_until_it_is_advanced() -> None:
    clock = FixedClockAdapter()

    assert clock.now_datetime_utc() == clock.now_datetime_utc() == FIRST_DATETIME_UTC
    clock.advance(timedelta(hours=1))
    assert clock.now_datetime_utc() == FIRST_DATETIME_UTC + timedelta(hours=1)


def test_the_sequence_gives_identifiers_that_count_up() -> None:
    generator = SequenceUuidGeneratorAdapter()

    assert [generator.new_uuid().int for _ in range(3)] == [1, 2, 3]
