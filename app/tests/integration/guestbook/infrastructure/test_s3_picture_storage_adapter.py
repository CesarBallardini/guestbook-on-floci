"""Integration tests: the picture storage adapter, against the emulator's S3.

Each test gets a new bucket, removed afterwards.
"""

import time
import uuid
from typing import TYPE_CHECKING

import boto3
import pytest

from guestbook.domain.errors import StorageError
from guestbook.domain.picture import MAX_PICTURE_BYTES, Picture
from guestbook.infrastructure.s3_picture_storage_adapter import (
    CONNECT_TIMEOUT_SECONDS,
    MAX_ATTEMPTS,
    S3PictureStorageAdapter,
)
from tests.contracts import PictureStorageContractMixin
from tests.integration.conftest import S3_ENDPOINT_URL
from tests.samples import PNG_FORMAT

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def emulator_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # The emulator takes any keys; boto3 insists on having some.
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'test')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'test')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')


@pytest.fixture
def picture_storage() -> Iterator[S3PictureStorageAdapter]:
    bucket_name = f'guestbook-test-{uuid.uuid4().hex}'
    client = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
    client.create_bucket(Bucket=bucket_name)
    yield S3PictureStorageAdapter(bucket_name, S3_ENDPOINT_URL)
    for stored in client.list_objects_v2(Bucket=bucket_name).get('Contents', []):
        client.delete_object(Bucket=bucket_name, Key=stored['Key'])
    client.delete_bucket(Bucket=bucket_name)


class TestS3PictureStorageAdapter(PictureStorageContractMixin):
    """The adapter does everything the in-memory fake does, for every accepted format."""

    @pytest.fixture
    def contract_storage(self, picture_storage: S3PictureStorageAdapter) -> S3PictureStorageAdapter:
        return picture_storage


def test_a_picture_as_big_as_allowed_makes_the_round_trip(picture_storage: S3PictureStorageAdapter) -> None:
    picture = Picture(b'\x89PNG\r\n\x1a\n'.ljust(MAX_PICTURE_BYTES, b'\0'), PNG_FORMAT)

    picture_storage.save('big.png', picture)

    assert picture_storage.load('big.png') == picture


def test_a_bucket_that_is_not_there_is_reported_as_a_storage_error(png_bytes: bytes) -> None:
    nowhere = S3PictureStorageAdapter(f'guestbook-test-missing-{uuid.uuid4().hex}', S3_ENDPOINT_URL)

    with pytest.raises(StorageError):
        nowhere.save('a-key.png', Picture(png_bytes, PNG_FORMAT))
    with pytest.raises(StorageError):
        nowhere.load('a-key.png')


def test_the_type_stored_next_to_the_bytes_is_not_what_decides_the_format() -> None:
    # Somebody who can write to the bucket says an object is a web page.
    bucket_name = f'guestbook-test-{uuid.uuid4().hex}'
    client = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
    client.create_bucket(Bucket=bucket_name)
    try:
        client.put_object(Bucket=bucket_name, Key='a-key.png', Body=b'<script>', ContentType='text/html')
        client.put_object(Bucket=bucket_name, Key='a-key.html', Body=b'<script>', ContentType='text/html')
        picture_storage = S3PictureStorageAdapter(bucket_name, S3_ENDPOINT_URL)

        assert picture_storage.load('a-key.png') == Picture(b'<script>', PNG_FORMAT)
        # Not the key of a picture: nothing is handed back.
        assert picture_storage.load('a-key.html') is None
    finally:
        for key in ('a-key.png', 'a-key.html'):
            client.delete_object(Bucket=bucket_name, Key=key)
        client.delete_bucket(Bucket=bucket_name)


def test_an_s3_that_cannot_be_reached_is_reported_without_a_long_wait() -> None:
    # Nothing listens on port 1.
    nowhere = S3PictureStorageAdapter('a-bucket', 'http://127.0.0.1:1')
    start_seconds = time.monotonic()

    with pytest.raises(StorageError):
        nowhere.load('a-key.png')

    # Each attempt may take its time limit, plus the pause before the next one. Measured: 9
    # seconds, against 15 with boto3's own settings here and 110 when S3 does not answer at all.
    assert time.monotonic() - start_seconds < MAX_ATTEMPTS * (CONNECT_TIMEOUT_SECONDS + 3)
