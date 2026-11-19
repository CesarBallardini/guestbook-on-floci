"""Unit tests for the use case "a visitor looks at the picture of a message"."""

import pytest

from guestbook.domain.picture import Picture
from guestbook.use_cases.get_picture import GetPictureUseCase
from tests.fakes import InMemoryPictureStorageAdapter
from tests.samples import PNG_FORMAT

pytestmark = pytest.mark.unit

A_PICTURE_KEY = '0' * 32 + '.png'


def test_getting_a_picture_returns_what_was_stored(
    picture_storage: InMemoryPictureStorageAdapter, png_bytes: bytes
) -> None:
    picture_storage.save(A_PICTURE_KEY, Picture(png_bytes, PNG_FORMAT))

    assert GetPictureUseCase(picture_storage).get_picture(A_PICTURE_KEY) == Picture(png_bytes, PNG_FORMAT)


def test_a_key_with_no_picture_gives_none(picture_storage: InMemoryPictureStorageAdapter) -> None:
    assert GetPictureUseCase(picture_storage).get_picture(A_PICTURE_KEY) is None
    assert picture_storage.loaded_keys == [A_PICTURE_KEY]


def test_a_text_that_is_not_a_picture_key_never_reaches_the_storage(
    picture_storage: InMemoryPictureStorageAdapter,
) -> None:
    assert GetPictureUseCase(picture_storage).get_picture('../../etc/passwd') is None
    assert picture_storage.loaded_keys == []
