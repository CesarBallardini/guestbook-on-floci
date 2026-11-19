"""Unit tests for the use case "a visitor signs the guestbook"."""

from datetime import timedelta

import pytest

from guestbook.domain.errors import InvalidMessageError, StorageError
from guestbook.domain.input_ports import SignGuestbookRequestDto
from guestbook.domain.message import Message
from guestbook.domain.picture import Picture
from guestbook.use_cases.sign_guestbook import SignGuestbookUseCase
from tests.fakes import (
    FIRST_DATETIME_UTC,
    FixedClockAdapter,
    InMemoryMessageRepository,
    InMemoryPictureStorageAdapter,
    SequenceUuidGeneratorAdapter,
)
from tests.samples import PNG_FORMAT

pytestmark = pytest.mark.unit


def test_signing_stores_the_message_trimmed_and_posted_at_the_time_the_clock_shows(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
) -> None:
    sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto(' Ada ', ' Hello '))

    assert message_repository.messages == [Message('Ada', 'Hello', FIRST_DATETIME_UTC, None)]
    assert picture_storage.pictures == {}


def test_each_message_is_posted_at_the_time_it_was_signed(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    clock: FixedClockAdapter,
) -> None:
    sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Ada', 'First'))
    clock.advance(timedelta(minutes=5))
    sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Bob', 'Second'))

    assert [message.posted_datetime_utc for message in message_repository.messages] == [
        FIRST_DATETIME_UTC,
        FIRST_DATETIME_UTC + timedelta(minutes=5),
    ]


def test_signing_with_a_picture_stores_it_under_a_key_made_from_a_new_identifier(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
    png_bytes: bytes,
) -> None:
    sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Ada', 'Look', png_bytes))

    first_key = '00000000000000000000000000000001.png'
    assert message_repository.messages[0].picture_key == first_key
    assert picture_storage.pictures == {first_key: Picture(png_bytes, PNG_FORMAT)}


def test_two_pictures_get_different_keys(
    sign_guestbook_use_case: SignGuestbookUseCase, picture_storage: InMemoryPictureStorageAdapter, png_bytes: bytes
) -> None:
    sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Ada', 'Look', png_bytes))
    sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Bob', 'Look too', png_bytes))

    assert list(picture_storage.pictures) == [
        '00000000000000000000000000000001.png',
        '00000000000000000000000000000002.png',
    ]


def test_a_message_that_breaks_a_rule_stores_nothing(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
) -> None:
    with pytest.raises(InvalidMessageError):
        sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Ada', 'Look', b'not an image'))

    assert message_repository.messages == []
    assert picture_storage.pictures == {}


def test_a_message_repository_that_fails_is_reported_as_such(
    sign_guestbook_use_case: SignGuestbookUseCase, message_repository: InMemoryMessageRepository
) -> None:
    message_repository.is_available = False

    with pytest.raises(StorageError):
        sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Ada', 'Hello'))


def test_when_the_message_cannot_be_stored_its_picture_is_removed_again(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
    png_bytes: bytes,
) -> None:
    message_repository.is_available = False

    with pytest.raises(StorageError):
        sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Ada', 'Look', png_bytes))

    assert picture_storage.pictures == {}


class PictureStorageThatCannotRemove(InMemoryPictureStorageAdapter):
    """A picture storage that keeps pictures and fails to let go of them."""

    def delete(self, picture_key: str) -> None:
        raise StorageError(f'The picture {picture_key} could not be removed.')


def test_when_neither_the_message_can_be_stored_nor_the_picture_removed_the_message_is_what_is_reported(
    message_repository: InMemoryMessageRepository,
    clock: FixedClockAdapter,
    uuid_generator: SequenceUuidGeneratorAdapter,
    png_bytes: bytes,
) -> None:
    picture_storage = PictureStorageThatCannotRemove()
    use_case = SignGuestbookUseCase(message_repository, picture_storage, clock, uuid_generator)
    message_repository.is_available = False

    with pytest.raises(StorageError, match='The message could not be stored'):
        use_case.sign_guestbook(SignGuestbookRequestDto('Ada', 'Look', png_bytes))


def test_when_the_message_cannot_be_stored_the_other_pictures_stay(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
    png_bytes: bytes,
) -> None:
    sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Ada', 'Look', png_bytes))
    message_repository.is_available = False

    with pytest.raises(StorageError):
        sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Grace', 'Look too', png_bytes))

    assert len(picture_storage.pictures) == 1


def test_when_the_picture_cannot_be_stored_the_message_is_not_stored_either(
    sign_guestbook_use_case: SignGuestbookUseCase,
    message_repository: InMemoryMessageRepository,
    picture_storage: InMemoryPictureStorageAdapter,
    png_bytes: bytes,
) -> None:
    picture_storage.is_available = False

    with pytest.raises(StorageError):
        sign_guestbook_use_case.sign_guestbook(SignGuestbookRequestDto('Ada', 'Look', png_bytes))

    assert message_repository.messages == []
