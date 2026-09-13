"""
FieldOfficer (technician profile) data-access layer.

Mirrors `user_repository.py`: no commits/rollbacks here — the service layer
owns the transaction.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.field_officer import FieldOfficer
from app.models.user import ApprovalStatus


class TechnicianRepository:
    def __init__(self, db: Session):
        self._db = db

    def create(self, field_officer: FieldOfficer) -> FieldOfficer:
        self._db.add(field_officer)
        self._db.flush()
        return field_officer

    def get_by_id(self, field_officer_id: uuid.UUID) -> FieldOfficer | None:
        return self._db.get(FieldOfficer, field_officer_id)

    def get_by_user_id(self, user_id: uuid.UUID) -> FieldOfficer | None:
        stmt = select(FieldOfficer).where(FieldOfficer.user_id == user_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def list_pending(self) -> list[FieldOfficer]:
        """FieldOfficers awaiting admin approval — backed by
        ix_field_officers_approval_status."""
        stmt = select(FieldOfficer).where(FieldOfficer.approval_status == ApprovalStatus.PENDING)
        return list(self._db.execute(stmt).scalars().all())
