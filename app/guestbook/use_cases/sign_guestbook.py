"""Use case: a visitor signs the guestbook."""

from typing import TYPE_CHECKING

from guestbook.domain.errors import StorageError
from guestbook.domain.message import Message, new_message
from guestbook.domain.picture import picture_key_for

if TYPE_CHECKING:
    from guestbook.domain.input_ports import SignGuestbookRequestDto
    from guestbook.domain.output_ports import ClockPort, MessageWriterPort, PictureWriterPort, UuidGeneratorPort


class SignGuestbookUseCase:
    """Implements SignGuestbookPort."""

    def __init__(
        self,
        message_writer: MessageWriterPort,
        picture_writer: PictureWriterPort,
        clock: ClockPort,
        uuid_generator: UuidGeneratorPort,
    ) -> None:
        """Remember where messages and pictures go, and who tells the time and names pictures."""
        self._message_writer = message_writer
        self._picture_writer = picture_writer
        self._clock = clock
        self._uuid_generator = uuid_generator

    def sign_guestbook(self, request_dto: SignGuestbookRequestDto) -> None:
        """Check the message against the rules, then store its picture and the message itself.

        Raises:
            InvalidMessageError: The message breaks one of the guestbook's rules. Nothing is stored.
            StorageError: The picture or the message could not be stored. A picture whose message
                could not be stored is removed again.
        """
        new = new_message(request_dto.author, request_dto.body, request_dto.picture_content)
        picture_key = None
        if new.picture:
            picture_key = picture_key_for(self._uuid_generator.new_uuid(), new.picture)
            # The picture first: a message never points at a picture that isn't there.
            self._picture_writer.save(picture_key, new.picture)
        try:
            self._message_writer.add(Message(new.author, new.body, self._clock.now_datetime_utc(), picture_key))
        except StorageError:
            if picture_key:
                self._remove_picture_nobody_points_at(picture_key)
            raise

    def _remove_picture_nobody_points_at(self, picture_key: str) -> None:
        try:
            self._picture_writer.delete(picture_key)
        except StorageError:
            # The visitor is told about the message, which is what failed first. The picture
            # stays where it is: no message points at it, so nobody can ask for it.
            return
