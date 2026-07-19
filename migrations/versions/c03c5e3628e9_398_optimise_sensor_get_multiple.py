"""Add a composite index on `SensorDataRecord`' "sensor_uid" and "timestamp" columns

Revision ID: c03c5e3628e9
Revises: a5c9f317bcea
Create Date: 2026-07-19 14:30:26.841596

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c03c5e3628e9'
down_revision: Union[str, None] = 'a5c9f317bcea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("sensor_records") as batch_op:
        batch_op.create_index(
            "idx_sensor_records_sensor_uid_timestamp", ["sensor_uid", "timestamp"], unique=False)

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("sensor_records") as batch_op:
        batch_op.drop_index("idx_sensor_records_sensor_uid_timestamp")


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
