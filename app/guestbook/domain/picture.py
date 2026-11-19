"""The rules for pictures: which formats the guestbook accepts, and the keys they are kept under.

Everything about a format is in one row of PICTURE_FORMATS. Accepting another format is one
more row: no rule below names a format.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from guestbook.domain.errors import InvalidMessageError

if TYPE_CHECKING:
    from uuid import UUID

MAX_PICTURE_MEGABYTES = 2
MAX_PICTURE_BYTES = MAX_PICTURE_MEGABYTES * 1024 * 1024

_UUID_HEX_LENGTH = 32
_LOWERCASE_HEX_DIGITS = frozenset('0123456789abcdef')


@dataclass(frozen=True)
class PictureSignature:
    """Bytes a file of some format always has, each at a fixed place: (offset, bytes) pairs."""

    parts: tuple[tuple[int, bytes], ...]

    def matches(self, content: bytes) -> bool:
        """Tell whether a content has every part of the signature in its place."""
        return all(content[offset : offset + len(expected)] == expected for offset, expected in self.parts)


@dataclass(frozen=True)
class PictureFormat:
    """One picture format the guestbook accepts."""

    name: str
    content_type: str
    # Every extension files of this format go by. The first is the one new keys get.
    extensions: tuple[str, ...]
    signatures: tuple[PictureSignature, ...]

    @property
    def extension(self) -> str:
        """The extension the key of a new picture of this format gets."""
        return self.extensions[0]

    def matches(self, content: bytes) -> bool:
        """Tell whether a content starts as a file of this format does."""
        return any(signature.matches(content) for signature in self.signatures)


PICTURE_FORMATS: tuple[PictureFormat, ...] = (
    PictureFormat('PNG', 'image/png', ('png',), (PictureSignature(((0, b'\x89PNG\r\n\x1a\n'),)),)),
    PictureFormat('JPEG', 'image/jpeg', ('jpg', 'jpeg'), (PictureSignature(((0, b'\xff\xd8\xff'),)),)),
    PictureFormat(
        'GIF', 'image/gif', ('gif',), (PictureSignature(((0, b'GIF87a'),)), PictureSignature(((0, b'GIF89a'),)))
    ),
    # A RIFF container (which also holds WAV and AVI) that says WEBP after its length field.
    PictureFormat('WebP', 'image/webp', ('webp',), (PictureSignature(((0, b'RIFF'), (8, b'WEBP'))),)),
)


@dataclass(frozen=True)
class Picture:
    """An image and the format it is in."""

    content: bytes
    picture_format: PictureFormat

    @property
    def content_type(self) -> str:
        """The media type a browser is told the image has."""
        return self.picture_format.content_type


def picture_format_of(content: bytes) -> PictureFormat | None:
    """Tell an image's format from its bytes, or None when it isn't an accepted one.

    The browser's word for the type is not trusted: the bytes decide.
    """
    return next((picture_format for picture_format in PICTURE_FORMATS if picture_format.matches(content)), None)


def accepted_format_names() -> str:
    """Name the accepted formats in a sentence: 'PNG, JPEG, GIF or WebP'."""
    *first_names, last_name = (picture_format.name for picture_format in PICTURE_FORMATS)
    return f'{", ".join(first_names)} or {last_name}'


def new_picture(content: bytes) -> Picture:
    """Check the bytes of a picture against the rules and return the picture with its format.

    Raises:
        InvalidMessageError: The picture is too big or not in an accepted format.
    """
    if len(content) > MAX_PICTURE_BYTES:
        raise InvalidMessageError(f'A picture can have up to {MAX_PICTURE_MEGABYTES} MB.')
    picture_format = picture_format_of(content)
    if picture_format is None:
        raise InvalidMessageError(f'A picture must be a {accepted_format_names()} image.')
    return Picture(content, picture_format)


def picture_key_for(picture_uuid: UUID, picture: Picture) -> str:
    """Make the key a picture is kept under: its identifier, with the extension of its format."""
    return f'{picture_uuid.hex}.{picture.picture_format.extension}'


def picture_format_of_key(key: str) -> PictureFormat | None:
    """Tell the format of the picture kept under a key, which is what the key's extension says.

    None when the extension is not an accepted format's. Whatever keeps pictures uses this to
    hand a picture back with its format, instead of trusting a type stored next to the bytes.
    """
    _name, separator, extension = key.rpartition('.')
    if not separator:
        return None
    return next((picture_format for picture_format in PICTURE_FORMATS if extension in picture_format.extensions), None)


def is_picture_key(key: str) -> bool:
    """Tell whether a text has the shape of a key: an identifier and an accepted extension."""
    identifier, _separator, _extension = key.partition('.')
    return (
        len(identifier) == _UUID_HEX_LENGTH
        and set(identifier) <= _LOWERCASE_HEX_DIGITS
        # One dot only: what follows the first is the whole extension.
        and key.count('.') == 1
        and picture_format_of_key(key) is not None
    )
