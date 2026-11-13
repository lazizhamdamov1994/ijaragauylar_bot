"""product_photos -> product_media (rasm va video), kind ustuni

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_pg_objects(old: str, new: str) -> None:
    op.execute(f"ALTER TABLE {new} RENAME CONSTRAINT pk_{old} TO pk_{new}")
    op.execute(
        f"ALTER TABLE {new} RENAME CONSTRAINT fk_{old}_product_id_products TO fk_{new}_product_id_products"
    )
    op.execute(f"ALTER SEQUENCE {old}_id_seq RENAME TO {new}_id_seq")


def upgrade() -> None:
    op.rename_table("product_photos", "product_media")
    if op.get_bind().dialect.name == "postgresql":
        _rename_pg_objects("product_photos", "product_media")
    with op.batch_alter_table("product_media") as batch:
        batch.add_column(sa.Column("kind", sa.String(length=10), server_default="photo", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("product_media") as batch:
        batch.drop_column("kind")
    op.rename_table("product_media", "product_photos")
    if op.get_bind().dialect.name == "postgresql":
        _rename_pg_objects("product_media", "product_photos")
