"""The rules for messages: what one is, and what makes a new one acceptable."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from guestbook.domain.errors import InvalidMessageError
from guestbook.domain.picture import new_picture

if TYPE_CHECKING:
    from datetime import datetime

    from guestbook.domain.picture import Picture

MAX_AUTHOR_LENGTH = 60
MAX_BODY_LENGTH = 500
# No keyboard types it, and places that keep text commonly refuse it: it marks the end of one.
_NUL_CHARACTER = '\x00'


@dataclass(frozen=True)
class NewMessage:
    """A message that passed the rules and isn't posted yet."""

    author: str
    body: str
    picture: Picture | None


@dataclass
class Message:
    """A posted message. `picture_key` names its picture where pictures are kept, if it has one.

    Two messages with the same content are equal. The class is not frozen, unlike the value
    objects around it: whatever keeps messages may need to attach its own bookkeeping to them.
    """

    author: str
    body: str
    posted_datetime_utc: datetime
    picture_key: str | None


def new_message(author: str, body: str, picture_content: bytes = b'') -> NewMessage:
    """Check a new message against the rules and return it with its spaces trimmed.

    Args:
        author: Who signs.
        body: What they say.
        picture_content: The bytes of an optional picture. Empty means no picture.

    Raises:
        InvalidMessageError: A text is empty, too long or has a NUL character, or the picture
            is too big or not in an accepted format.
    """
    author = author.strip()
    body = body.strip()
    if _NUL_CHARACTER in author or _NUL_CHARACTER in body:
        raise InvalidMessageError('A message cannot have the NUL character in its name or its text.')
    if not author or len(author) > MAX_AUTHOR_LENGTH:
        raise InvalidMessageError(f'A message needs a name of 1 to {MAX_AUTHOR_LENGTH} characters.')
    if not body or len(body) > MAX_BODY_LENGTH:
        raise InvalidMessageError(f'A message needs a text of 1 to {MAX_BODY_LENGTH} characters.')
    return NewMessage(author, body, new_picture(picture_content) if picture_content else None)
