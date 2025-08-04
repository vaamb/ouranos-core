"""empty message

Revision ID: 71e1ef7da0b8
Revises: fc8f9d8bf7b6
Create Date: 2025-08-04 21:59:46.950827

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "71e1ef7da0b8"
down_revision: Union[str, None] = "fc8f9d8bf7b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("association_hardware_measures") as batch_op:
        batch_op.add_column(sa.Column("id", sa.Integer(), autoincrement=True))
        batch_op.create_primary_key("id_pk", columns=["id"])
        batch_op.alter_column("id", nullable=False)

    op.rename_table("association_actuators_plants", "association_hardware_plants")
    with op.batch_alter_table("association_hardware_plants") as batch_op:
        batch_op.add_column(sa.Column("id", sa.Integer(), autoincrement=True))
        batch_op.create_primary_key("id_pk", columns=["id"])
        batch_op.alter_column("id", nullable=False)

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("association_hardware_measures") as batch_op:
        batch_op.drop_column("id")

    op.rename_table("association_hardware_plants", "association_actuators_plants")
    with op.batch_alter_table("association_actuators_plants") as batch_op:
        batch_op.drop_column("id")

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
