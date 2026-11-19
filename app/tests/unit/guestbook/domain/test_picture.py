"""Unit tests for the rules for pictures."""

from uuid import UUID

import pytest

from guestbook.domain.errors import InvalidMessageError
from guestbook.domain.picture import (
    MAX_PICTURE_BYTES,
    PICTURE_FORMATS,
    Picture,
    PictureFormat,
    PictureSignature,
    accepted_format_names,
    is_picture_key,
    new_picture,
    picture_format_of,
    picture_format_of_key,
    picture_key_for,
)
from tests.samples import PNG_FORMAT

pytestmark = pytest.mark.unit

A_UUID = UUID('019a9d2e-0000-7000-8000-00000000abcd')


@pytest.mark.parametrize(
    ('content', 'expected'),
    [
        (b'\x89PNG\r\n\x1a\n...', 'image/png'),
        (b'\xff\xd8\xff\xe0...', 'image/jpeg'),
        (b'GIF87a...', 'image/gif'),
        (b'GIF89a...', 'image/gif'),
        (b'RIFF\x00\x00\x00\x00WEBPVP8 ', 'image/webp'),
        (b'RIFF\x00\x00\x00\x00WAVEfmt ', None),
        (b'RIFF', None),
        (b'%PDF-1.7', None),
        (b'', None),
    ],
)
def test_the_format_of_a_picture_comes_from_its_bytes(content: bytes, expected: str | None) -> None:
    picture_format = picture_format_of(content)

    assert (picture_format.content_type if picture_format else None) == expected


def test_a_signature_needs_every_part_in_its_place() -> None:
    signature = PictureSignature(((0, b'AB'), (4, b'CD')))

    assert signature.matches(b'AB..CD')
    assert not signature.matches(b'AB..XX')
    assert not signature.matches(b'ABCD')


def test_the_formats_have_different_types_and_extensions() -> None:
    assert len({picture_format.content_type for picture_format in PICTURE_FORMATS}) == len(PICTURE_FORMATS)
    assert len({picture_format.extension for picture_format in PICTURE_FORMATS}) == len(PICTURE_FORMATS)


def test_the_accepted_formats_are_named_in_a_sentence() -> None:
    assert accepted_format_names() == 'PNG, JPEG, GIF or WebP'


def test_a_new_picture_gets_the_type_its_bytes_show(png_bytes: bytes) -> None:
    assert new_picture(png_bytes) == Picture(png_bytes, PNG_FORMAT)


def test_a_file_that_is_not_an_image_is_refused() -> None:
    with pytest.raises(InvalidMessageError, match='must be a PNG, JPEG, GIF or WebP image'):
        new_picture(b'<script>alert(1)</script>')


def test_a_picture_over_the_size_limit_is_refused(png_bytes: bytes) -> None:
    with pytest.raises(InvalidMessageError, match='up to 2 MB'):
        new_picture(png_bytes + b'\0' * MAX_PICTURE_BYTES)


def test_a_picture_of_exactly_the_size_limit_is_accepted(png_bytes: bytes) -> None:
    content = png_bytes + b'\0' * (MAX_PICTURE_BYTES - len(png_bytes))

    assert len(new_picture(content).content) == MAX_PICTURE_BYTES


@pytest.mark.parametrize('picture_format', PICTURE_FORMATS, ids=[f.name for f in PICTURE_FORMATS])
def test_a_picture_key_is_the_identifier_with_the_extension_of_the_format(picture_format: PictureFormat) -> None:
    key = picture_key_for(A_UUID, Picture(b'...', picture_format))

    assert key == f'019a9d2e00007000800000000000abcd.{picture_format.extension}'
    assert is_picture_key(key)


@pytest.mark.parametrize(
    'key',
    [
        '',
        'picture.png',
        '../../etc/passwd',
        'a' * 32 + '.exe',
        'A' * 32 + '.png',
        'a' * 32,
        'a' * 32 + '.png.png',
        'a' * 31 + '/.png',
    ],
)
def test_a_text_of_another_shape_is_not_a_picture_key(key: str) -> None:
    assert not is_picture_key(key)


@pytest.mark.parametrize('picture_format', PICTURE_FORMATS, ids=[f.name for f in PICTURE_FORMATS])
def test_the_format_of_a_key_is_the_one_its_extension_says(picture_format: PictureFormat) -> None:
    for extension in picture_format.extensions:
        assert picture_format_of_key(f'anything.{extension}') == picture_format


def test_a_format_can_go_by_several_extensions_and_new_keys_get_the_first() -> None:
    jpeg_format = picture_format_of_key('anything.jpeg')

    assert jpeg_format is not None
    assert jpeg_format == picture_format_of_key('anything.jpg')
    assert picture_key_for(A_UUID, Picture(b'...', jpeg_format)).endswith('.jpg')
    assert is_picture_key(f'{A_UUID.hex}.jpeg')


def test_no_extension_belongs_to_two_formats() -> None:
    extensions = [extension for picture_format in PICTURE_FORMATS for extension in picture_format.extensions]

    assert len(set(extensions)) == len(extensions)


@pytest.mark.parametrize('key', ['', 'png', 'a-key', 'a-key.', 'a-key.exe', 'a-key.PNG', 'a-key.png.txt'])
def test_a_key_without_the_extension_of_an_accepted_format_has_no_format(key: str) -> None:
    assert picture_format_of_key(key) is None


def test_a_picture_tells_the_media_type_of_its_format(png_bytes: bytes) -> None:
    assert new_picture(png_bytes).content_type == 'image/png'
