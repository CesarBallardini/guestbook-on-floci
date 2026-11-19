"""What Alembic runs to reach the database: `alembic upgrade head`, from the app's folder.

The database is the one DATABASE_URL names, unless whoever calls Alembic from Python set
`sqlalchemy.url` in its configuration (the integration tests do, for their throwaway database).
"""

import logging
import os

from alembic import context

from guestbook.infrastructure.database.engine import create_database_engine
from guestbook.infrastructure.database.orm_mapping import metadata

if context.config.cmd_opts is not None:
    # Run from the command line: say which revisions run. A deploy reads this to know whether
    # anything changed.
    logging.basicConfig(format='%(levelname)s %(message)s')
    logging.getLogger('alembic').setLevel(logging.INFO)

database_url = context.config.get_main_option('sqlalchemy.url') or os.environ['DATABASE_URL']
engine = create_database_engine(database_url)

if context.is_offline_mode():
    # --sql: print the statements instead of running them.
    context.configure(url=engine.url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
