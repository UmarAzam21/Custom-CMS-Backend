"""add profile_image to admin_users

Revision ID: f12a3e4b7d29
Revises: bc824a76dd00
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f12a3e4b7d29"
down_revision: Union[str, Sequence[str], None] = "bc824a76dd00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("profile_image", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_users", "profile_image")
