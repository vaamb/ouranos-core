"""empty message

Revision ID: 17c093dc188e
Revises: 71e1ef7da0b8
Create Date: 2025-10-25 14:50:20.084541

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision: str = "17c093dc188e"
down_revision: Union[str, None] = "71e1ef7da0b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str) -> None:
    globals()["upgrade_%s" % engine_name]()

def downgrade(engine_name: str) -> None:
    globals()["downgrade_%s" % engine_name]()


def upgrade_ecosystems() -> None:
    with op.batch_alter_table("association_hardware_measures") as batch_op:
        batch_op.create_unique_constraint("uq_hardware_uid_measure_id", ["hardware_uid", "measure_id"])

    with op.batch_alter_table("association_hardware_plants") as batch_op:
        batch_op.create_unique_constraint("uq_hardware_uid_plant_uid", ["hardware_uid", "plant_uid"])

def downgrade_ecosystems() -> None:
    with op.batch_alter_table("association_hardware_measures") as batch_op:
        batch_op.drop_constraint("uq_hardware_uid_measure_id", type_="unique")

    with op.batch_alter_table("association_hardware_plants") as batch_op:
        batch_op.drop_constraint("uq_hardware_uid_plant_uid", type_="unique")


def upgrade_app() -> None:
    with op.batch_alter_table("association_user_recap") as batch_op:
        batch_op.add_column(sa.Column("id", sa.Integer(), autoincrement=True))
        batch_op.create_primary_key("id_pk", columns=["id"])
        batch_op.alter_column("id", nullable=False)
        batch_op.create_unique_constraint("uq_user_uid_channel_id", ["user_uid", "channel_id"])

    with op.batch_alter_table("association_wiki_tag_article") as batch_op:
        batch_op.add_column(sa.Column("id", sa.Integer(), autoincrement=True))
        batch_op.create_primary_key("id_pk", columns=["id"])
        batch_op.alter_column("id", nullable=False)
        batch_op.create_unique_constraint("uq_tag_id_article_id", ["tag_id", "article_id"])

    with op.batch_alter_table("association_wiki_tag_picture") as batch_op:
        batch_op.add_column(sa.Column("id", sa.Integer(), autoincrement=True))
        batch_op.create_primary_key("id_pk", columns=["id"])
        batch_op.alter_column("id", nullable=False)
        batch_op.create_unique_constraint("uq_tag_id_picture_id", ["tag_id", "picture_id"])

    with op.batch_alter_table("association_wiki_tag_topic") as batch_op:
        batch_op.add_column(sa.Column("id", sa.Integer(), autoincrement=True))
        batch_op.create_primary_key("id_pk", columns=["id"])
        batch_op.alter_column("id", nullable=False)
        batch_op.create_unique_constraint("uq_tag_id_topic_id", ["tag_id", "topic_id"])

def downgrade_app() -> None:
    with op.batch_alter_table("association_wiki_tag_topic") as batch_op:
        batch_op.drop_constraint("uq_tag_id_topic_id", type_="unique")
        batch_op.drop_column("id")

    with op.batch_alter_table("association_wiki_tag_picture") as batch_op:
        batch_op.drop_constraint("uq_tag_id_picture_id", type_="unique")
        batch_op.drop_column("id")

    with op.batch_alter_table("association_wiki_tag_article") as batch_op:
        batch_op.drop_constraint("uq_tag_id_article_id", type_="unique")
        batch_op.drop_column("id")

    with op.batch_alter_table("association_user_recap") as batch_op:
        batch_op.drop_constraint("uq_user_uid_channel_id", type_="unique")
        batch_op.drop_column("id")


def upgrade_system() -> None:
    pass

def downgrade_system() -> None:
    pass


def upgrade_archive() -> None:
    pass

def downgrade_archive() -> None:
    pass
