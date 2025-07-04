"""More logical primary keys

Revision ID: 500b502bb663
Revises: a721d18f48c6
Create Date: 2024-08-06 23:33:57.399899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '500b502bb663'
down_revision: Union[str, None] = 'a721d18f48c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("hardware") as batch_op:
        batch_op.drop_constraint("pk_hardware", type_="primary")
        batch_op.create_primary_key("pk_hardware", ["uid"])

    with op.batch_alter_table("environment_parameters") as batch_op:
        batch_op.drop_column("id")
        batch_op.create_primary_key("pk_environment_parameters", ["ecosystem_uid", "parameter"])

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("hardware") as batch_op:
        batch_op.drop_constraint("pk_hardware", type_="primary")
        batch_op.create_primary_key("pk_hardware", ["uid", "ecosystem_uid"])

    with op.batch_alter_table("environment_parameters") as batch_op:
        batch_op.drop_constraint("pk_environment_parameters", type_="primary")
        batch_op.add_column(sa.Column("id", sa.INTEGER(), nullable=False, primary_key=True))


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
