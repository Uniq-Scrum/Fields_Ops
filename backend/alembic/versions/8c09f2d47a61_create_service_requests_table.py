"""create service_requests table

Revision ID: 8c09f2d47a61
Revises: e2702f96a61d
Create Date: 2026-09-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8c09f2d47a61"
down_revision: Union[str, None] = "e2702f96a61d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_text", sa.String(length=2000), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="RECEIVED",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            name="fk_service_requests_customer_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_service_requests_customer_created_at",
        "service_requests",
        ["customer_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_service_requests_customer_created_at", table_name="service_requests"
    )
    op.drop_table("service_requests")