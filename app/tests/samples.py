"""Values the tests name often."""

from guestbook.domain.picture import PICTURE_FORMATS

PNG_FORMAT = next(picture_format for picture_format in PICTURE_FORMATS if picture_format.extension == 'png')
GIF_FORMAT = next(picture_format for picture_format in PICTURE_FORMATS if picture_format.extension == 'gif')
