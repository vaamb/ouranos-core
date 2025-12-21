"""Add "active" field to hardware table

Revision ID: 226f20fc21cd
Revises: 53d80616ed16
Create Date: 2025-12-21 14:35:25.360586

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision: str = '226f20fc21cd'
down_revision: Union[str, None] = '53d80616ed16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("hardware") as batch_op:
        batch_op.add_column(sa.Column("active", sa.Boolean(), nullable=False, default=True))

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("hardware") as batch_op:
        batch_op.drop_column("active")


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
