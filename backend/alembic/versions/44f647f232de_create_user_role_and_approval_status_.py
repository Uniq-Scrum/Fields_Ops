"""create user_role and approval_status enums and users table

Revision ID: 44f647f232de
Revises:
Create Date: 2026-09-13 15:15:57.561489

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '44f647f232de'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Native Postgres enum types, matching app/models/user.py exactly.
# create_type/checkfirst are handled explicitly below (not by SQLAlchemy's
# implicit DDL) so a type shared by more than one table (approval_status is
# also used by field_officers, added in the next migration) is created and
# dropped exactly once, deterministically.
user_role_enum = postgresql.ENUM(
    "CUSTOMER", "TECHNICIAN", "ADMIN", name="user_role", create_type=False
)
approval_status_enum = postgresql.ENUM(
    "PENDING", "APPROVED", "REJECTED", name="approval_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    user_role_enum.create(bind, checkfirst=True)
    approval_status_enum.create(bind, checkfirst=True)

    # Shared trigger function: sets updated_at to the real wall-clock time of
    # this UPDATE, regardless of whether the write came through the ORM or
    # raw SQL. Uses clock_timestamp(), not now(): now()/CURRENT_TIMESTAMP is
    # fixed for the whole enclosing transaction, so two UPDATEs issued
    # moments apart in the same transaction would otherwise get identical
    # updated_at values. Owned by this migration; field_officers (next
    # migration) reuses it rather than declaring its own copy.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
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
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("phone", name="uq_users_phone"),
    )

    # email/phone are already indexed implicitly by their UNIQUE constraints
    # (Postgres backs every unique constraint with an index) — role and
    # approval_status get their own indexes since they're filtered on
    # directly (e.g. "all pending technicians") but are low-cardinality, not
    # unique.
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_approval_status", "users", ["approval_status"])

    op.execute(
        """
        CREATE TRIGGER trg_users_set_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users;")
    op.drop_index("ix_users_approval_status", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")

    # Safe only once field_officers (which also uses this function) has
    # already been dropped by downgrading that migration first.
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")

    bind = op.get_bind()
    approval_status_enum.drop(bind, checkfirst=True)
    user_role_enum.drop(bind, checkfirst=True)
