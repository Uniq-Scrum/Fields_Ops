"""
Technician-facing routes.

Currently exposes only the authenticated technician's own FieldOfficer
profile, gated by `require_role(UserRole.TECHNICIAN)` — this exists to
demonstrate and test TECHNICIAN-only RBAC enforcement. Technician
discovery/dispatch/matching endpoints belong to the matching team and are
not implemented here.

Deliberately not gated on FieldOfficer.approval_status: a technician whose
account is still PENDING may still read their own profile (e.g. to see
their approval status) — approval only matters for endpoints that grant
dispatch-eligible capability, which don't exist yet in this codebase.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.user import User, UserRole
from app.schemas.technician import FieldOfficerResponse
from app.services.technician_service import TechnicianService
from app.utils.exceptions import AppException

router = APIRouter(prefix="/api/v1/technicians", tags=["technicians"])


@router.get(
    "/me",
    response_model=FieldOfficerResponse,
    summary="Get the authenticated technician's own FieldOfficer profile (TECHNICIAN only)",
)
def read_own_field_officer(
    current_user: User = Depends(require_role(UserRole.TECHNICIAN)),
    db: Session = Depends(get_db),
) -> FieldOfficerResponse:
    field_officer = TechnicianService(db).get_by_user_id(current_user.id)
    if field_officer is None:
        # Cannot happen for a normally-registered technician (User and
        # FieldOfficer are created atomically) — guards against future
        # data drift rather than a reachable client-driven case.
        raise AppException("Field officer profile not found", status_code=404)
    return FieldOfficerResponse.model_validate(field_officer)
