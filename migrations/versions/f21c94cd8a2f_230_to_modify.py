"""to modify

Revision ID: f21c94cd8a2f
Revises: 1e8ec14d8183
Create Date: 2025-04-25 21:09:55.254789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import gaia_validators as gv

from ouranos.core.database.models.app import CalendarEventVisibility
from ouranos.core.database.models.types import SQLIntEnum


# revision identifiers, used by Alembic.
revision: str = 'f21c94cd8a2f'
down_revision: Union[str, None] = '1e8ec14d8183'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    # Change gv.WarningLevel storage repr
    with op.batch_alter_table('warnings') as batch_op:
        batch_op.alter_column('level',
                              existing_type=sa.VARCHAR(length=8),
                              type_=SQLIntEnum(gv.WarningLevel),
                              existing_nullable=False,
                              existing_default=gv.WarningLevel.low)
    with op.batch_alter_table('warnings') as batch_op:
        batch_op.alter_column('level',
                              existing_type=sa.VARCHAR(length=8),
                              type_=SQLIntEnum(gv.WarningLevel),
                              existing_nullable=False,
                              existing_default=gv.WarningLevel.low)

def downgrade_ecosystems() -> None:
    # Change gv.WarningLevel storage repr
    with op.batch_alter_table('warnings') as batch_op:
        batch_op.alter_column('level',
                              existing_type=SQLIntEnum(gv.WarningLevel),
                              type_=sa.VARCHAR(length=8),
                              existing_nullable=False,
                              existing_default=gv.WarningLevel.low)
    with op.batch_alter_table('sensor_alarms') as batch_op:
        batch_op.alter_column('level',
                              existing_type=SQLIntEnum(gv.WarningLevel),
                              type_=sa.VARCHAR(length=8),
                              existing_nullable=False,
                              existing_default=gv.WarningLevel.low)


def upgrade_app() -> None:
    # Change gv.WarningLevel storage repr
    with op.batch_alter_table('calendar_events') as batch_op:
        batch_op.alter_column('level',
                              existing_type=sa.VARCHAR(length=8),
                              type_=SQLIntEnum(gv.WarningLevel),
                              existing_nullable=False,
                              existing_default=gv.WarningLevel.low)
    with op.batch_alter_table('flash_message') as batch_op:
        batch_op.alter_column('level',
                              existing_type=sa.VARCHAR(length=8),
                              type_=SQLIntEnum(gv.WarningLevel),
                              existing_nullable=False,
                              existing_default=gv.WarningLevel.low)

    # Change CalendarEventVisibility storage repr
    with op.batch_alter_table('calendar_events') as batch_op:
        batch_op.alter_column('visibility',
                              existing_type=sa.VARCHAR(length=7),
                              type_=SQLIntEnum(CalendarEventVisibility),
                              existing_nullable=False,
                              existing_default=CalendarEventVisibility.users)

def downgrade_app() -> None:
    # Change gv.WarningLevel storage repr
    with op.batch_alter_table('calendar_events') as batch_op:
        batch_op.alter_column('level',
                              existing_type=SQLIntEnum(gv.WarningLevel),
                              type_=sa.VARCHAR(length=8),
                              existing_nullable=False,
                              existing_default=gv.WarningLevel.low)
    with op.batch_alter_table('flash_message') as batch_op:
        batch_op.alter_column('level',
                              existing_type=SQLIntEnum(gv.WarningLevel),
                              type_=sa.VARCHAR(length=8),
                              existing_nullable=False,
                              existing_default=gv.WarningLevel.low)

    # Change CalendarEventVisibility storage repr
    with op.batch_alter_table('calendar_events') as batch_op:
        batch_op.alter_column('visibility',
                              existing_type=SQLIntEnum(CalendarEventVisibility),
                              type_=sa.VARCHAR(length=7),
                              existing_nullable=False,
                              existing_default=CalendarEventVisibility.users)


def upgrade_system() -> None:
    pass

def downgrade_system() -> None:
    pass


def upgrade_archive() -> None:
    pass

def downgrade_archive() -> None:
    pass
