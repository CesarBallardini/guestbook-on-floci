"""The tables, and how SQLAlchemy maps the domain's classes onto them.

The mapping is imperative: the domain's `Message` stays a plain dataclass that imports nothing
(though not a frozen one: SQLAlchemy keeps its own state on each mapped object),
and this module, on the infrastructure's side, tells SQLAlchemy which column each of its
fields lives in. The repository then stores and loads `Message` objects themselves; there is
no second class for a row.

The tables themselves are created by the migrations, which compare with `metadata`.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Identity,
    MetaData,
    Table,
    Text,
    TypeDecorator,
    inspect,
)
from sqlalchemy.orm import registry

from guestbook.domain.message import MAX_AUTHOR_LENGTH, MAX_BODY_LENGTH, Message

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

metadata = MetaData()
_mapper_registry = registry(metadata=metadata)


class UtcDateTimeTypeDecorator(TypeDecorator[datetime]):
    """A moment in time: stored as `timestamptz`, and always handed back aware, in UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:  # noqa: ARG002
        """Refuse a time without a zone: the database would guess one."""
        if value is not None and value.tzinfo is None:
            raise ValueError('A naive datetime cannot be stored: give it a timezone first.')
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:  # noqa: ARG002
        """Convert from the session's zone, which is what the driver returns."""
        return None if value is None else value.astimezone(UTC)


message_table = Table(
    'message',
    metadata,
    Column('id', BigInteger, Identity(always=True), primary_key=True),
    Column('author', Text, nullable=False),
    Column('body', Text, nullable=False),
    Column('posted_datetime_utc', UtcDateTimeTypeDecorator, nullable=False),
    Column('picture_key', Text, nullable=True),
    # The rules are the domain's. These keep out what did not go through them: a row written by
    # hand, or by a later mistake in the app.
    CheckConstraint(f'char_length(author) between 1 and {MAX_AUTHOR_LENGTH}', name='message_author_length'),
    CheckConstraint(f'char_length(body) between 1 and {MAX_BODY_LENGTH}', name='message_body_length'),
)


def start_orm_mapping() -> None:
    """Map the domain's classes onto the tables. Safe to call again: it maps once.

    A message has no identifier in the domain. The table's own goes to a private attribute,
    `_row_id`, which SQLAlchemy needs to tell rows apart and nothing else reads.
    """
    if inspect(Message, raiseerr=False) is None:
        _mapper_registry.map_imperatively(Message, message_table, properties={'_row_id': message_table.c.id})
