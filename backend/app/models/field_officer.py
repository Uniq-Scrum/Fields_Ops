"""
FieldOfficer model — technician-specific profile data.

A one-to-one extension of `User` (never a replacement for it): every
FieldOfficer row belongs to exactly one User with role=TECHNICIAN, enforced
by a unique + not-null foreign key. The FK is `ON DELETE CASCADE` (set in
the Alembic migration) so a FieldOfficer row can never outlive its User —
there is no code path that deletes a User while leaving its FieldOfficer
behind.
"""
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import approval_status_enum, ApprovalStatus


class FieldOfficer(Base):
    """Technician profile: skills, availability, and field-vetting approval."""

    __tablename__ = "field_officers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Postgres native array: skills are a small, flat, unordered tag set
    # queried with containment (`@>` / `ANY`) by the matching service, not a
    # relation requiring joins — a GIN index (added in the migration)
    # supports that lookup efficiently without a normalized skills table.
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list, server_default=text("'{}'")
    )

    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Distinct from User.approval_status: a technician's *account* can be
    # approved while their field-officer vetting (skills/background check)
    # is still pending dispatch eligibility. Reuses the same ApprovalStatus
    # enum/type rather than declaring a second one.
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        approval_status_enum, nullable=False, default=ApprovalStatus.PENDING
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Maintained by the `set_updated_at()` trigger (see the Alembic
    # migration) — same mechanism as User.updated_at, not a separate one.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="field_officer")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<FieldOfficer id={self.id} user_id={self.user_id}>"
