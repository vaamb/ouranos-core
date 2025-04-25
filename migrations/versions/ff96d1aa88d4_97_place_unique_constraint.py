"""Add unique constraint in the places table

Revision ID: ff96d1aa88d4
Revises: e932af6045f2
Create Date: 2024-08-15 19:45:16.315772

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ff96d1aa88d4'
down_revision: Union[str, None] = 'e932af6045f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("places") as batch_op:
        batch_op.create_unique_constraint("uq_places_engine_uid", ["engine_uid", "name"])

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("places") as batch_op:
        batch_op.drop_constraint("uq_places_engine_uid", type_="unique")


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
