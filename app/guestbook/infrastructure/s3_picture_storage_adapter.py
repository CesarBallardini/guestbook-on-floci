"""The pictures, in an S3 bucket."""

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from guestbook.domain.errors import StorageError
from guestbook.domain.picture import Picture, picture_format_of_key

# How long to wait for S3, and how often to ask. With boto3's own settings a visitor waits up
# to 110 seconds (measured) before being told that S3 does not answer. A picture has at most
# 2 MB and S3 is near the app, so these limits are far from what a working S3 needs.
CONNECT_TIMEOUT_SECONDS = 3
READ_TIMEOUT_SECONDS = 10
# The first try and one more, for a failure that passes.
MAX_ATTEMPTS = 2


class S3PictureStorageAdapter:
    """Implements PictureWriterPort and PictureReaderPort with one object of a bucket per picture."""

    def __init__(self, bucket_name: str, endpoint_url: str | None = None) -> None:
        """Connect to S3.

        Args:
            bucket_name: The bucket. It must exist.
            endpoint_url: Where S3 is, for an emulator. None means AWS.
        """
        self._client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            config=Config(
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                read_timeout=READ_TIMEOUT_SECONDS,
                retries={'mode': 'standard', 'max_attempts': MAX_ATTEMPTS},
            ),
        )
        self._bucket_name = bucket_name

    def save(self, picture_key: str, picture: Picture) -> None:
        """Store a picture under a key.

        Raises:
            StorageError: S3 could not store it.
        """
        try:
            self._client.put_object(
                Bucket=self._bucket_name, Key=picture_key, Body=picture.content, ContentType=picture.content_type
            )
        except (BotoCoreError, ClientError) as error:
            raise StorageError('The picture could not be stored.') from error

    def delete(self, picture_key: str) -> None:
        """Remove the picture stored under a key. A key with no picture is not an error.

        Raises:
            StorageError: S3 could not remove it.
        """
        try:
            self._client.delete_object(Bucket=self._bucket_name, Key=picture_key)
        except (BotoCoreError, ClientError) as error:
            raise StorageError('The picture could not be removed.') from error

    def load(self, picture_key: str) -> Picture | None:
        """Return the picture stored under a key, or None when there is none.

        The format comes from the key. The content type S3 keeps with the object is for whoever
        looks at the bucket; it is not read back, so nobody who can write to the bucket decides
        what a browser is told.

        Raises:
            StorageError: S3 could not be read.
        """
        picture_format = picture_format_of_key(picture_key)
        if picture_format is None:
            return None
        try:
            answer = self._client.get_object(Bucket=self._bucket_name, Key=picture_key)
            return Picture(answer['Body'].read(), picture_format)
        except self._client.exceptions.NoSuchKey:
            return None
        except (BotoCoreError, ClientError) as error:
            raise StorageError('The picture could not be read.') from error
