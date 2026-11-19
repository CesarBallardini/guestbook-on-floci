"""What gunicorn runs, with uvicorn workers: the guestbook, put together from the environment.

This is the one place that knows every layer: it makes the infrastructure adapters, hands them
to the use cases, and hands the use cases to the web.

DATABASE_URL and PICTURE_BUCKET are required. S3_ENDPOINT_URL is for an emulator: without it,
the pictures go to AWS. The S3 credentials come from the instance's role, as boto3 finds them.

The database's tables are not made here: `alembic upgrade head` does it, before the app starts.

What the app has to say goes to standard output, one event per line, from LOG_LEVEL up (INFO
when not set). Where that ends up is for whoever starts the app to decide, not for the app.
"""

import logging
import os
import sys

from guestbook.infrastructure.database.engine import create_database_engine, create_session_factory
from guestbook.infrastructure.database.sqlalchemy_message_repository import SqlAlchemyMessageRepository
from guestbook.infrastructure.s3_picture_storage_adapter import S3PictureStorageAdapter
from guestbook.infrastructure.system_clock_adapter import SystemClockAdapter
from guestbook.infrastructure.uuid7_generator_adapter import Uuid7GeneratorAdapter
from guestbook.infrastructure.web.fastapi_app import create_fastapi_app
from guestbook.use_cases.get_picture import GetPictureUseCase
from guestbook.use_cases.list_latest_messages import ListLatestMessagesUseCase
from guestbook.use_cases.sign_guestbook import SignGuestbookUseCase

logging.basicConfig(
    stream=sys.stdout,
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S%z',
)

message_repository = SqlAlchemyMessageRepository(
    create_session_factory(create_database_engine(os.environ['DATABASE_URL']))
)
picture_storage = S3PictureStorageAdapter(os.environ['PICTURE_BUCKET'], os.environ.get('S3_ENDPOINT_URL'))

application = create_fastapi_app(
    SignGuestbookUseCase(message_repository, picture_storage, SystemClockAdapter(), Uuid7GeneratorAdapter()),
    ListLatestMessagesUseCase(message_repository),
    GetPictureUseCase(picture_storage),
)
