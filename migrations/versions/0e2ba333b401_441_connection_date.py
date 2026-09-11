"""Add "connection_date" columns to `Engine` and `Ecosystem`

Revision ID: 0e2ba333b401
Revises: b46729dca456
Create Date: 2026-09-11 19:37:16.784200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision: str = '0e2ba333b401'
down_revision: Union[str, None] = 'b46729dca456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("engines") as batch_op:
        batch_op.add_column(
            sa.Column(
                "connection_date", sa.DateTime(), nullable=False,
                server_default=sa.func.current_timestamp()
            ),
            insert_after="registration_date",
        )

    with op.batch_alter_table("ecosystems") as batch_op:
        batch_op.add_column(
            sa.Column(
                "connection_date", sa.DateTime(), nullable=False,
                server_default=sa.func.current_timestamp()
            ),
            insert_after="registration_date",
        )

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("engines") as batch_op:
        batch_op.drop_column("connection_date")

    with op.batch_alter_table("ecosystems") as batch_op:
        batch_op.drop_column("connection_date")


def upgrade_app() -> None:
    pass

def downgrade_app() -> None:
    pass


def upgrade_system() -> None:
    pass

def downgrade_system() -> None:
    pass


def upgrade_archive() -> None:
    pass

def downgrade_archive() -> None:
    pass
