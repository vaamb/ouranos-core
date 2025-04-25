"""Use system UID as primary key

Revision ID: e932af6045f2
Revises: 500b502bb663
Create Date: 2024-08-11 00:13:28.531171

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e932af6045f2'
down_revision: Union[str, None] = '500b502bb663'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    pass

def downgrade_ecosystems() -> None:
    pass


def upgrade_app() -> None:
    pass

def downgrade_app() -> None:
    pass


def upgrade_system() -> None:
    with op.batch_alter_table("systems") as batch_op:
        batch_op.add_column(sa.Column("hostname", sa.String(length=32), nullable=False, default="_default"))
        batch_op.drop_column( "id")
        batch_op.create_primary_key("pk_systems", ["uid"])

def downgrade_system() -> None:
    with op.batch_alter_table("systems") as batch_op:
        batch_op.drop_constraint("pk_systems", type_="primary")
        batch_op.add_column(sa.Column("id", sa.INTEGER(), nullable=False, primary_key=True))
        batch_op.drop_column("hostname")


def upgrade_archive() -> None:
    pass

def downgrade_archive() -> None:
    pass
