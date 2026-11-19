"""Create the message table.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        'message',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column('author', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('posted_datetime_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('picture_key', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Undo this revision."""
    op.drop_table('message')
