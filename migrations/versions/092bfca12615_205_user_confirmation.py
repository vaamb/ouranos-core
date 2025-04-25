"""Change user confirmation logic

Revision ID: 092bfca12615
Revises: d3c34effeefa
Create Date: 2025-03-07 23:23:07.599120

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '092bfca12615'
down_revision: Union[str, None] = 'd3c34effeefa'
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
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('registration_datetime',
                              new_column_name='created_at')
        batch_op.drop_column('confirmed')
        batch_op.add_column(sa.Column('confirmed_at', sa.DateTime(), nullable=True, default=None),
                            insert_before='firstname')

def downgrade_app() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('created_at',
                              new_column_name='registration_datetime')
        batch_op.drop_column('confirmed_at')
        batch_op.add_column(sa.Column('confirmed', sa.Boolean(), nullable=False, default=False),
                            insert_before='firstname')


def upgrade_system() -> None:
    pass

def downgrade_system() -> None:
    pass


def upgrade_archive() -> None:
    pass

def downgrade_archive() -> None:
    pass
