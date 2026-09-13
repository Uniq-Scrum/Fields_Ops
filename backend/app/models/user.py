"""
User model — every account on the platform (customers, technicians, admins).

`UserRole` and `ApprovalStatus` are defined here, once, as the single source
of truth: they back both the SQLAlchemy column (as native PostgreSQL enum
types, so the database rejects an invalid value even from a raw SQL client)
and the Pydantic schemas in `app/schemas/`, which import them from here
rather than redeclaring them.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    TECHNICIAN = "TECHNICIAN"
    ADMIN = "ADMIN"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Native PostgreSQL enum types. `create_type=False`: the type is created
# explicitly by the Alembic migration (see database/migrations, i.e.
# backend/alembic/versions/), not implicitly by SQLAlchemy's create_all —
# this keeps enum creation/drop deterministic and prevents two models that
# share a type from racing to create/drop it.
user_role_enum = Enum(
    UserRole,
    name="user_role",
    create_type=False,
    validate_strings=True,
)

approval_status_enum = Enum(
    ApprovalStatus,
    name="approval_status",
    create_type=False,
    validate_strings=True,
)


class User(Base):
    """A platform account. Exactly one role; approval workflow is role-dependent."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Stored lowercased/normalized by the service layer; uniqueness is
    # enforced at the database level (see the Alembic migration), not only
    # by an application-level pre-check, so concurrent registrations with
    # the same email can never both succeed.
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    # Never the plaintext password — see app/core/security.py.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(user_role_enum, nullable=False)

    # Account-level approval workflow. CUSTOMER accounts are auto-approved
    # on registration; TECHNICIAN/ADMIN accounts start PENDING and require
    # an existing admin to approve them — registration itself never grants
    # elevated privilege (see app/services/user_service.py).
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        approval_status_enum, nullable=False, default=ApprovalStatus.PENDING
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Maintained exclusively by the `set_updated_at()` database trigger
    # (created in the Alembic migration) — not an ORM-level `onupdate`, so
    # there is exactly one mechanism (correct for ORM writes, raw SQL, and
    # admin tools alike) rather than two that could disagree.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    field_officer: Mapped["FieldOfficer | None"] = relationship(
        "FieldOfficer",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
