"""Catch up

Revision ID: 1e8ec14d8183
Revises: 092bfca12615
Create Date: 2025-04-25 00:15:55.043347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e8ec14d8183'
down_revision: Union[str, None] = '092bfca12615'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    # Remove unused health_records table
    with op.batch_alter_table('health_records') as batch_op:
        batch_op.drop_index('ix_health_records_ecosystem_uid')
    op.drop_table('health_records')

    # Remove warnings' updated_on
    with op.batch_alter_table('warnings') as batch_op:
        batch_op.drop_column('updated_on')

def downgrade_ecosystems() -> None:
    # Add warnings' updated_on
    with op.batch_alter_table('warnings') as batch_op:
        batch_op.add_column(sa.Column('updated_on', sa.DATETIME(), nullable=True))

    # Add health_records table
    op.create_table(
        "health_records",
        sa.Column("id", sa.INTEGER(), nullable=False),
        sa.Column("timestamp", sa.DATETIME(), nullable=False),
        sa.Column("green", sa.INTEGER(), nullable=False),
        sa.Column("necrosis", sa.INTEGER(), nullable=False),
        sa.Column("health_index", sa.INTEGER(), nullable=False),
        sa.Column("ecosystem_uid", sa.VARCHAR(length=8), nullable=False),
        sa.ForeignKeyConstraint(["ecosystem_uid"],["ecosystems.uid"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table('health_records') as batch_op:
        batch_op.create_index("ix_health_records_ecosystem_uid", ["ecosystem_uid"], unique=False)


def upgrade_app() -> None:
    # Add calendar events visibility
    with op.batch_alter_table('calendar_events') as batch_op:
        batch_op.add_column(sa.Column(
            'visibility',
            sa.Enum('public', 'users', 'private', name='calendareventvisibility'),
            server_default='users',
            nullable=False))

    # Make services name unique
    with op.batch_alter_table('services') as batch_op:
        batch_op.create_unique_constraint('uq_services_name',  ['name'])

    # Change telegram_id type
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('telegram_id',
                              existing_type=sa.String(length=16),
                              type_=sa.Integer(),
                              existing_nullable=True)

def downgrade_app() -> None:
    # Remove calendar events visibility
    with op.batch_alter_table('calendar_events') as batch_op:
        batch_op.drop_column('visibility')

    # Remove services name uniqueness
    with op.batch_alter_table('services') as batch_op:
        batch_op.drop_constraint('uq_services_name', type_='unique')

    # Change telegram_id type
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('telegram_id',
                              existing_type=sa.Integer(),
                              type_=sa.String(length=16),
                              existing_nullable=True)


def upgrade_system() -> None:
    pass

def downgrade_system() -> None:
    pass


def upgrade_archive() -> None:
    # Remove unused health_records_archive table
    with op.batch_alter_table("health_records_archive") as batch_op:
        batch_op.drop_index("ix_health_records_archive_ecosystem_uid")
    op.drop_table('health_records_archive')

def downgrade_archive() -> None:
    # Add health_records_archive table
    op.create_table('health_records_archive',
        sa.Column('ecosystem_uid', sa.VARCHAR(length=8), nullable=False),
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('timestamp', sa.DATETIME(), nullable=False),
        sa.Column('green', sa.INTEGER(), nullable=False),
        sa.Column('necrosis', sa.INTEGER(), nullable=False),
        sa.Column('health_index', sa.INTEGER(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('health_records_archive') as batch_op:
        batch_op.create_index('ix_health_records_archive_ecosystem_uid',  ['ecosystem_uid'], unique=False)
