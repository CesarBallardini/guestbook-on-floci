"""Stand-ins for what the guestbook asks of the outside.

They are real implementations of the output ports, kept in memory. The tests hand them over
where the app hands over a database, a bucket, the machine's clock and random identifiers, so
nothing needs to be mocked or patched.

tests/contracts.py holds the tests that both a fake and the adapter it stands for must pass.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from guestbook.domain.errors import StorageError
from guestbook.domain.message import Message
from guestbook.domain.picture import Picture

FIRST_DATETIME_UTC = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


class InMemoryMessageRepository:
    """Implements MessageWriterPort and MessageReaderPort with a list.

    Set `is_available` to False to make it fail as a database that is down does.
    """

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.is_available = True

    def add(self, message: Message) -> None:
        if not self.is_available:
            raise StorageError('The message could not be stored.')
        self.messages.append(message)

    def latest(self, limit: int) -> list[Message]:
        if not self.is_available:
            raise StorageError('The messages could not be read.')
        return self.messages[::-1][:limit]


class InMemoryPictureStorageAdapter:
    """Implements PictureWriterPort and PictureReaderPort with a dictionary.

    Set `is_available` to False to make it fail as a bucket that can't be reached does.
    """

    def __init__(self) -> None:
        self.pictures: dict[str, Picture] = {}
        self.loaded_keys: list[str] = []
        self.is_available = True

    def save(self, picture_key: str, picture: Picture) -> None:
        if not self.is_available:
            raise StorageError('The picture could not be stored.')
        self.pictures[picture_key] = picture

    def delete(self, picture_key: str) -> None:
        if not self.is_available:
            raise StorageError('The picture could not be removed.')
        self.pictures.pop(picture_key, None)

    def load(self, picture_key: str) -> Picture | None:
        if not self.is_available:
            raise StorageError('The picture could not be read.')
        self.loaded_keys.append(picture_key)
        return self.pictures.get(picture_key)


class FixedClockAdapter:
    """Implements ClockPort with a clock that shows the time it is told, until told another."""

    def __init__(self, now_datetime_utc: datetime = FIRST_DATETIME_UTC) -> None:
        self._now_datetime_utc = now_datetime_utc

    def now_datetime_utc(self) -> datetime:
        return self._now_datetime_utc

    def advance(self, elapsed_duration: timedelta) -> None:
        self._now_datetime_utc += elapsed_duration


class SequenceUuidGeneratorAdapter:
    """Implements UuidGeneratorPort with identifiers that count up from 1."""

    def __init__(self) -> None:
        self._last_number = 0

    def new_uuid(self) -> UUID:
        self._last_number += 1
        return UUID(int=self._last_number)
