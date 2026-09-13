"""create field_officers table

Revision ID: e2702f96a61d
Revises: 44f647f232de
Create Date: 2026-09-13 15:15:58.275875

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e2702f96a61d'
down_revision: Union[str, None] = '44f647f232de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reuses the approval_status type created in the previous migration —
# create_type=False here means this migration never creates or drops it.
approval_status_enum = postgresql.ENUM(
    "PENDING", "APPROVED", "REJECTED", name="approval_status", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "field_officers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "skills",
            postgresql.ARRAY(sa.String(length=100)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "is_available", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "approval_status",
            approval_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_field_officers_user_id_users",
            ondelete="CASCADE",
        ),
        # UNIQUE on user_id enforces the one-to-one User <-> FieldOfficer
        # relationship at the database level, not only in the ORM.
        sa.UniqueConstraint("user_id", name="uq_field_officers_user_id"),
    )

    # GIN index for containment queries against the skills array, e.g.
    # "technicians who have skill X" (WHERE skills @> ARRAY['electrical']).
    op.create_index(
        "ix_field_officers_skills",
        "field_officers",
        ["skills"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_field_officers_is_available", "field_officers", ["is_available"]
    )
    op.create_index(
        "ix_field_officers_approval_status", "field_officers", ["approval_status"]
    )

    op.execute(
        """
        CREATE TRIGGER trg_field_officers_set_updated_at
        BEFORE UPDATE ON field_officers
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_field_officers_set_updated_at ON field_officers;"
    )
    op.drop_index("ix_field_officers_approval_status", table_name="field_officers")
    op.drop_index("ix_field_officers_is_available", table_name="field_officers")
    op.drop_index("ix_field_officers_skills", table_name="field_officers")
    op.drop_table("field_officers")
