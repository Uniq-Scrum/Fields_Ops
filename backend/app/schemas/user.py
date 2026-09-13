"""
User-facing Pydantic schemas.

`UserResponse` is the ONLY shape a User is ever serialized to over the API —
it deliberately has no `password_hash` field, so there is no risk of a
route accidentally leaking it by reusing a schema that has one.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import ApprovalStatus, UserRole


class UserResponse(BaseModel):
    """Safe, public representation of a User. Never includes password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    phone: str
    role: UserRole
    approval_status: ApprovalStatus
    created_at: datetime
    updated_at: datetime
