"""Where the integration tests find the emulator.

They need the emulator running and `terraform apply` done (the RDS instance must exist). Each
test works in a database or a bucket of its own, made for it and removed afterwards, so the
guestbook's own data is never touched.

The defaults are the emulator's addresses as this machine sees them. To point the tests
elsewhere, set GUESTBOOK_TEST_POSTGRES_URL (a URL of the `postgres` database, with a user that
may create databases) and GUESTBOOK_TEST_S3_ENDPOINT_URL.
"""

import os
from pathlib import Path

# The app's folder, where alembic.ini is.
APP_DIR = Path(__file__).parents[2]

POSTGRES_URL = os.environ.get(
    'GUESTBOOK_TEST_POSTGRES_URL', 'postgresql://postgres:development-only@127.0.0.1:7001/postgres'
)
S3_ENDPOINT_URL = os.environ.get('GUESTBOOK_TEST_S3_ENDPOINT_URL', 'http://127.0.0.1:4566')
