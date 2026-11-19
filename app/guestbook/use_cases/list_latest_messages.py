"""Use case: a visitor reads the guestbook."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from guestbook.domain.message import Message
    from guestbook.domain.output_ports import MessageReaderPort

SHOWN_MESSAGES = 50


class ListLatestMessagesUseCase:
    """Implements ListLatestMessagesPort."""

    def __init__(self, message_reader: MessageReaderPort, shown_messages: int = SHOWN_MESSAGES) -> None:
        """Remember where the messages are and how many the guestbook shows."""
        self._message_reader = message_reader
        self._shown_messages = shown_messages

    def list_latest_messages(self) -> list[Message]:
        """Return the messages the guestbook shows, the newest first.

        Raises:
            StorageError: The messages could not be read.
        """
        return self._message_reader.latest(self._shown_messages)
