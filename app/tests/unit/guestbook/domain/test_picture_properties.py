"""Property-based tests for the rules for pictures: they hold for any bytes, key and identifier."""

import re
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from guestbook.domain.errors import InvalidMessageError
from guestbook.domain.picture import (
    MAX_PICTURE_BYTES,
    PICTURE_FORMATS,
    Picture,
    PictureFormat,
    is_picture_key,
    new_picture,
    picture_format_of,
    picture_key_for,
)

pytestmark = pytest.mark.unit

# Written out here on purpose: an independent statement of what a key looks like.
KEY_SHAPE = re.compile(r'[0-9a-f]{32}\.(png|jpg|jpeg|gif|webp)')

any_format = st.sampled_from(PICTURE_FORMATS)
# Texts that look almost like keys, so that the edges are tried, mixed with any text at all.
almost_keys = st.from_regex(r'[0-9a-fA-F]{30,34}\.?(png|jpg|jpeg|gif|webp|exe|PNG)?', fullmatch=True)


@given(picture_uuid=st.uuids(), picture_format=any_format)
def test_every_key_made_for_a_picture_is_a_picture_key(picture_uuid: UUID, picture_format: PictureFormat) -> None:
    key = picture_key_for(picture_uuid, Picture(b'', picture_format))

    assert is_picture_key(key)
    assert KEY_SHAPE.fullmatch(key)


@given(first_uuid=st.uuids(), second_uuid=st.uuids(), picture_format=any_format)
def test_different_identifiers_give_different_keys(
    first_uuid: UUID, second_uuid: UUID, picture_format: PictureFormat
) -> None:
    picture = Picture(b'', picture_format)

    assert (picture_key_for(first_uuid, picture) == picture_key_for(second_uuid, picture)) == (
        first_uuid == second_uuid
    )


@given(text=st.one_of(st.text(max_size=60), almost_keys))
def test_a_text_is_a_picture_key_exactly_when_it_has_the_shape_of_one(text: str) -> None:
    assert is_picture_key(text) == (KEY_SHAPE.fullmatch(text) is not None)


@given(content=st.binary(max_size=64))
def test_any_bytes_are_either_a_picture_of_an_accepted_format_or_refused(content: bytes) -> None:
    try:
        picture = new_picture(content)
    except InvalidMessageError:
        assert picture_format_of(content) is None
    else:
        assert picture.content == content
        assert picture.content_type in {picture_format.content_type for picture_format in PICTURE_FORMATS}


@given(picture_format=any_format, rest=st.binary(max_size=64))
def test_a_file_that_starts_as_a_format_does_is_recognised_whatever_follows(
    picture_format: PictureFormat, rest: bytes
) -> None:
    signature = picture_format.signatures[0]
    start = bytearray(max(offset + len(part) for offset, part in signature.parts))
    for offset, part in signature.parts:
        start[offset : offset + len(part)] = part

    assert picture_format_of(bytes(start) + rest) == picture_format


@given(extra_bytes=st.integers(min_value=1, max_value=1024))
def test_a_picture_over_the_limit_is_refused_by_any_margin(extra_bytes: int) -> None:
    content = PICTURE_FORMATS[0].signatures[0].parts[0][1].ljust(MAX_PICTURE_BYTES + extra_bytes, b'\0')

    with pytest.raises(InvalidMessageError, match='up to 2 MB'):
        new_picture(content)
