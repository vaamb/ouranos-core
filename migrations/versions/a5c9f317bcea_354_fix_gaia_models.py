"""empty message

Revision ID: a5c9f317bcea
Revises: 226f20fc21cd
Create Date: 2026-04-05 10:11:32.753177

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision: str = 'a5c9f317bcea'
down_revision: Union[str, None] = '226f20fc21cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("weather_events") as batch_op:
        batch_op.drop_constraint("pk_pattern", type_="primary")

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("weather_events") as batch_op:
        batch_op.create_primary_key("pk_pattern", ["pattern"])


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
