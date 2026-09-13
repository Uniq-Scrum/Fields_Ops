"""
FieldOfficer (technician profile)-facing Pydantic schemas.

`FieldOfficerResponse` is the public representation of a FieldOfficer row —
used by a technician reading their own profile and by admin views. It has
no fields a client could use to set their own approval state.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import ApprovalStatus


class FieldOfficerResponse(BaseModel):
    """Safe, public representation of a FieldOfficer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    skills: list[str]
    is_available: bool
    approval_status: ApprovalStatus
    created_at: datetime
    updated_at: datetime
