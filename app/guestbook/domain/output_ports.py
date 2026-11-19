"""The guestbook's output ports: what the guestbook asks of the outside.

The domain owns them. The infrastructure implements them, and the use cases call them. Each
port is one thing a use case may need, so that a use case that only reads can't write.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from guestbook.domain.message import Message
    from guestbook.domain.picture import Picture


class MessageWriterPort(Protocol):
    """Keeps a posted message."""

    def add(self, message: Message) -> None:
        """Store one message.

        Raises:
            StorageError: The message could not be stored.
        """
        ...


class MessageReaderPort(Protocol):
    """Finds the messages that were kept."""

    def latest(self, limit: int) -> list[Message]:
        """Return up to `limit` messages, the newest first.

        Raises:
            StorageError: The messages could not be read.
        """
        ...


class PictureWriterPort(Protocol):
    """Keeps a picture, and lets go of one."""

    def save(self, picture_key: str, picture: Picture) -> None:
        """Store a picture under a key. The key's extension is that of the picture's format.

        Raises:
            StorageError: The picture could not be stored.
        """
        ...

    def delete(self, picture_key: str) -> None:
        """Remove the picture stored under a key. A key with no picture is not an error.

        Raises:
            StorageError: The picture could not be removed.
        """
        ...


class PictureReaderPort(Protocol):
    """Finds a picture that was kept."""

    def load(self, picture_key: str) -> Picture | None:
        """Return the picture stored under a key, or None when there is none.

        The picture's format is the one the key's extension says.

        Raises:
            StorageError: The pictures could not be read.
        """
        ...


class ClockPort(Protocol):
    """Tells the time."""

    def now_datetime_utc(self) -> datetime:
        """Return the present moment, aware, in UTC."""
        ...


class UuidGeneratorPort(Protocol):
    """Makes up identifiers."""

    def new_uuid(self) -> UUID:
        """Return an identifier nobody got before."""
        ...
