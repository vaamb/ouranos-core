"""empty message

Revision ID: fc8f9d8bf7b6
Revises: f21c94cd8a2f
Create Date: 2025-07-09 11:01:53.717908

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision: str = "fc8f9d8bf7b6"
down_revision: Union[str, None] = "f21c94cd8a2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("actuator_states") as batch_op:
        batch_op.create_unique_constraint(
            "uq_actuator_states_ecosystem_uid", ["ecosystem_uid", "type"])

    with op.batch_alter_table("environment_parameters") as batch_op:
        batch_op.create_unique_constraint(
            "uq_environment_parameters_ecosystem_uid", ["ecosystem_uid", "parameter"])

    with op.batch_alter_table("measures") as batch_op:
        batch_op.create_unique_constraint(
            "uq_measures_name", ["name"])

    with op.batch_alter_table("measures") as batch_op:
        batch_op.create_unique_constraint(
            "camera_pictures_info", ["ecosystem_uid", "camera_uid"])

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("actuator_states") as batch_op:
        batch_op.drop_constraint("uq_actuator_states_ecosystem_uid", type_="unique")

    with op.batch_alter_table("environment_parameters") as batch_op:
        batch_op.drop_constraint("uq_environment_parameters_ecosystem_uid", type_="unique")

    with op.batch_alter_table("measures") as batch_op:
        batch_op.drop_constraint("uq_measures_name", type_="unique")

    with op.batch_alter_table("measures") as batch_op:
        batch_op.drop_constraint("camera_pictures_info", type_="unique")


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
