"""Technician (FieldOfficer) business logic — currently read-only.

FieldOfficer creation happens exclusively inside
`UserService.register_user` (atomic with User creation for TECHNICIAN
accounts) — this service does not expose a separate create path, so a
FieldOfficer can never be created without its owning User.
"""
import uuid

from sqlalchemy.orm import Session

from app.models.field_officer import FieldOfficer
from app.repositories.technician_repository import TechnicianRepository


class TechnicianService:
    def __init__(self, db: Session):
        self._technicians = TechnicianRepository(db)

    def get_by_user_id(self, user_id: uuid.UUID) -> FieldOfficer | None:
        return self._technicians.get_by_user_id(user_id)

    def list_pending(self) -> list[FieldOfficer]:
        return self._technicians.list_pending()
