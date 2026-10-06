"""Sync table columns between `ActuatorRecord` and `ActuatorRecordArchive` DB models

Revision ID: 097f53d6e883
Revises: 7ff9fb8e67db
Create Date: 2026-10-06 20:37:33.417087

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision: str = '097f53d6e883'
down_revision: Union[str, None] = '7ff9fb8e67db'
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
    pass

def downgrade_app() -> None:
    pass


def upgrade_system() -> None:
    pass

def downgrade_system() -> None:
    pass


def upgrade_archive() -> None:
    with op.batch_alter_table("actuator_records_archive") as batch_op:
        batch_op.drop_column("actuator_uid")

def downgrade_archive() -> None:
    with op.batch_alter_table("actuator_records_archive") as batch_op:
        batch_op.add_column(
            sa.Column("actuator_uid", sa.String(length=16), index=True),
        )
