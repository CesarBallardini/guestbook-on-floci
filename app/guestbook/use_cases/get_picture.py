"""Use case: a visitor looks at the picture of a message."""

from typing import TYPE_CHECKING

from guestbook.domain.picture import is_picture_key

if TYPE_CHECKING:
    from guestbook.domain.output_ports import PictureReaderPort
    from guestbook.domain.picture import Picture


class GetPictureUseCase:
    """Implements GetPicturePort."""

    def __init__(self, picture_reader: PictureReaderPort) -> None:
        """Remember where the pictures are."""
        self._picture_reader = picture_reader

    def get_picture(self, picture_key: str) -> Picture | None:
        """Return the picture with that key, or None when there is none.

        A text that doesn't have the shape of a key never reaches the storage.

        Raises:
            StorageError: The pictures could not be read.
        """
        if not is_picture_key(picture_key):
            return None
        return self._picture_reader.load(picture_key)
