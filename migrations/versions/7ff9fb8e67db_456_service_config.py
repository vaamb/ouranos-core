"""empty message

Revision ID: 7ff9fb8e67db
Revises: 0e2ba333b401
Create Date: 2026-09-23 19:43:41.515452

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ff9fb8e67db'
down_revision: Union[str, None] = '0e2ba333b401'
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
    with op.batch_alter_table("services", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "in_config", sa.Boolean(), nullable=False,
                default=False, server_default=sa.sql.false(),
            ),
            insert_after="level",
        )

def downgrade_app() -> None:
    with op.batch_alter_table("services") as batch_op:
        batch_op.drop_column("in_config")


def upgrade_system() -> None:
    pass

def downgrade_system() -> None:
    pass


def upgrade_archive() -> None:
    pass

def downgrade_archive() -> None:
    pass
