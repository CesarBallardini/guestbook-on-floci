"""The guestbook's input ports: what the outside asks of the guestbook.

The domain owns them. The use cases implement them, and the web calls them.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from guestbook.domain.message import Message
    from guestbook.domain.picture import Picture


@dataclass(frozen=True)
class SignGuestbookRequestDto:
    """What a visitor sends to sign: unchecked texts and the bytes of an optional picture."""

    author: str
    body: str
    picture_content: bytes = b''


class SignGuestbookPort(Protocol):
    """A visitor signs the guestbook."""

    def sign_guestbook(self, request_dto: SignGuestbookRequestDto) -> None:
        """Store a new message, with its picture if it has one.

        Raises:
            InvalidMessageError: The message breaks one of the guestbook's rules.
            StorageError: The message or its picture could not be stored.
        """
        ...


class ListLatestMessagesPort(Protocol):
    """A visitor reads the guestbook."""

    def list_latest_messages(self) -> list[Message]:
        """Return the messages the guestbook shows, the newest first.

        Raises:
            StorageError: The messages could not be read.
        """
        ...


class GetPicturePort(Protocol):
    """A visitor looks at the picture of a message."""

    def get_picture(self, picture_key: str) -> Picture | None:
        """Return the picture with that key, or None when there is none.

        Raises:
            StorageError: The pictures could not be read.
        """
        ...
