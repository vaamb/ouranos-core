"""Make `gv.ClimateParameter` and `gv.WeatherParameter` plain strings

Revision ID: fcd8a54453e0
Revises: 643c5b344209
Create Date: 2026-11-25 20:54:53.719507

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fcd8a54453e0'
down_revision: Union[str, None] = '643c5b344209'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


# Frozen copy of the former `gv.ClimateParameter` column type
climate_parameter_enum = sa.Enum(
    "temperature", "humidity", "light", "wind", name="climateparameter")


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("environment_parameters") as batch_op:
        batch_op.alter_column(
            "parameter",
            existing_type=climate_parameter_enum,
            type_=sa.String(length=24),
            existing_nullable=False,
            postgresql_using="parameter::text",
        )
    # For PostgreSQL, drop the enum
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        climate_parameter_enum.drop(bind, checkfirst=True)

def downgrade_ecosystems() -> None:
    # For PostgreSQL, create the enum
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        climate_parameter_enum.create(bind, checkfirst=True)
    with op.batch_alter_table("environment_parameters") as batch_op:
        batch_op.alter_column(
            "parameter",
            existing_type=sa.String(length=24),
            type_=climate_parameter_enum,
            existing_nullable=False,
            postgresql_using="parameter::climateparameter",
        )


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
