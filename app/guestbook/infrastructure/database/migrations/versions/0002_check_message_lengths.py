"""Make the message table refuse texts the rules refuse.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply this revision."""
    # The limits as they were when this revision was written. A later change of the rules is
    # another revision; this one stays as it is.
    op.create_check_constraint('message_author_length', 'message', 'char_length(author) between 1 and 60')
    op.create_check_constraint('message_body_length', 'message', 'char_length(body) between 1 and 500')


def downgrade() -> None:
    """Undo this revision."""
    op.drop_constraint('message_body_length', 'message', type_='check')
    op.drop_constraint('message_author_length', 'message', type_='check')
