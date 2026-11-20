"""${message}

The releases before this one must still run on the schema it makes: a rollback leaves it in
place (expand and contract, docs/guestbook.md).

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """Apply this revision."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Undo this revision."""
    ${downgrades if downgrades else "pass"}
