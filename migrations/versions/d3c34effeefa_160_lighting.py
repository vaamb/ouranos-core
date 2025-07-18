"""Lightings to nycthemeral cycles

Revision ID: d3c34effeefa
Revises: ff96d1aa88d4
Create Date: 2025-01-23 10:23:06.786519

"""
from datetime import time
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import gaia_validators as gv


# revision identifiers, used by Alembic.
revision: str = 'd3c34effeefa'
down_revision: Union[str, None] = 'ff96d1aa88d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("ecosystems") as batch_op:
        batch_op.drop_column("day_start")
        batch_op.drop_column("night_start")

    with op.batch_alter_table("lightings") as batch_op:
        batch_op.drop_column("method")
        batch_op.add_column(
            sa.Column("span", sa.Enum(gv.NycthemeralSpanMethod),
                      nullable=False, default=gv.NycthemeralSpanMethod.fixed))
        batch_op.add_column(
            sa.Column("lighting", sa.Enum(gv.LightingMethod), nullable=False,
                      default=gv.LightingMethod.fixed))
        batch_op.add_column(
            sa.Column("day", sa.Time(), nullable=False, default=time(8)))
        batch_op.add_column(
            sa.Column("night", sa.Time(), nullable=False, default=time(20)))

    op.rename_table("lightings", "nycthemeral_cycles")

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("ecosystems") as batch_op:
        batch_op.add_column(
            sa.Column("day_start", sa.Time(), default=time(8), nullable=False))
        batch_op.add_column(sa.Column(
            "night_start", sa.Time(), default=time(20), nullable=False))

    with op.batch_alter_table("lightings") as batch_op:
        batch_op.drop_column("span")
        batch_op.drop_column("lighting")
        batch_op.drop_column("day")
        batch_op.drop_column("night")

    op.rename_table("nycthemeral_cycles", "lightings")


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
