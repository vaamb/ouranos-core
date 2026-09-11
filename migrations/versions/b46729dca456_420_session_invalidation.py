"""Add session token revocation logic

Revision ID: b46729dca456
Revises: c03c5e3628e9
Create Date: 2026-08-16 23:32:51.524457

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b46729dca456'
down_revision: Union[str, None] = 'c03c5e3628e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    pass

def downgrade_ecosystems() -> None:
    pass


def upgrade_app() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "sessions_valid_from", sa.DateTime(), nullable=False,
                server_default=sa.func.current_timestamp()))

def downgrade_app() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("sessions_valid_from")


def upgrade_system() -> None:
    pass

def downgrade_system() -> None:
    pass


def upgrade_archive() -> None:
    pass

def downgrade_archive() -> None:
    pass
