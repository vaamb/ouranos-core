"""Make `FlashMessage` an `ArchivableMixin`

Revision ID: 643c5b344209
Revises: 097f53d6e883
Create Date: 2026-10-25 20:10:25.821754

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '643c5b344209'
down_revision: Union[str, None] = '097f53d6e883'
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
    with op.batch_alter_table('flash_message') as batch_op:
        batch_op.drop_column('active')
        batch_op.add_column(
            sa.Column('inactivated_on', sa.DateTime(), nullable=True)
        )

def downgrade_app() -> None:
    with op.batch_alter_table('flash_message') as batch_op:
        batch_op.drop_column('inactivated_on')
        batch_op.add_column(
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.sql.true())
        )


def upgrade_system() -> None:
    pass

def downgrade_system() -> None:
    pass


def upgrade_archive() -> None:
    pass

def downgrade_archive() -> None:
    pass
