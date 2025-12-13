"""Add HardwareGroup and link it with related tables

Revision ID: 53d80616ed16
Revises: 17c093dc188e
Create Date: 2025-11-03 13:47:06.432432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "53d80616ed16"
down_revision: Union[str, None] = "17c093dc188e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    op.create_table(
        "association_hardware_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("hardware_uid", sa.VARCHAR(length=16), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_association_hardware_groups")),
        sa.ForeignKeyConstraint(
            ["group_id"], ["hardware_groups.id"],
            name=op.f("fk_association_hardware_groups_group_id_hardware_groups")),
        sa.ForeignKeyConstraint(
            ["hardware_uid"], ["hardware.uid"],
            name=op.f("fk_association_hardware_groups_hardware_uid_hardware")),
        if_not_exists=True,
    )

    with op.batch_alter_table("environment_parameters") as batch_op:
        batch_op.add_column(sa.Column("linked_actuator_group_increase_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_environment_parameters_linked_actuator_group_increase",
            "hardware_groups", ["linked_actuator_group_increase_id"], ["id"])
        batch_op.add_column(sa.Column("linked_actuator_group_decrease_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_environment_parameters_linked_actuator_group_decrease",
            "hardware_groups", ["linked_actuator_group_decrease_id"], ["id"])
        batch_op.add_column(sa.Column("linked_measure_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_environment_parameters_linked_measure_id_measures",
            "measures", ["linked_measure_id"], ["id"])

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("environment_parameters") as batch_op:
        batch_op.drop_column("linked_actuator_group_increase_id")
        batch_op.drop_column("linked_actuator_group_decrease_id")
        batch_op.drop_column("linked_measure_id")
    op.drop_table("association_hardware_groups", if_exists=True)


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
