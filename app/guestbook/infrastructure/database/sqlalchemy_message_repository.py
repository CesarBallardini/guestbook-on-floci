"""The messages, in the database.

The repository knows the database and the domain: it takes and returns domain objects. The
domain doesn't know it exists.
"""

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from guestbook.domain.errors import StorageError
from guestbook.domain.message import Message
from guestbook.infrastructure.database.orm_mapping import message_table, start_orm_mapping

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


class SqlAlchemyMessageRepository:
    """Implements MessageWriterPort and MessageReaderPort with the `message` table."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """Remember how to open a session. Each operation is one transaction of its own.

        Args:
            session_factory: As `create_session_factory` makes it.
        """
        start_orm_mapping()
        self._session_factory = session_factory

    def add(self, message: Message) -> None:
        """Store one message.

        Raises:
            StorageError: The database could not store it.
        """
        try:
            with self._session_factory.begin() as session:
                session.add(message)
        except SQLAlchemyError as error:
            raise StorageError('The message could not be stored.') from error

    def latest(self, limit: int) -> list[Message]:
        """Return up to `limit` messages, the newest first.

        Raises:
            StorageError: The database could not be read.
        """
        try:
            with self._session_factory() as session:
                messages = list(session.scalars(select(Message).order_by(message_table.c.id.desc()).limit(limit)))
                # Plain objects from here on: nothing that reads them goes back to the database.
                session.expunge_all()
                return messages
        except SQLAlchemyError as error:
            raise StorageError('The messages could not be read.') from error
