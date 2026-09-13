"""
Admin-facing routes.

Currently exposes only a read-only view of technicians pending approval,
gated by `require_role(UserRole.ADMIN)` — this exists to demonstrate and
test ADMIN-only RBAC enforcement. The approval/rejection action itself
belongs to whichever team owns the technician-vetting workflow and is not
implemented here.

There is no way to create an ADMIN account through any public API in this
codebase (see app/schemas/auth.py) — admin accounts are provisioned
out-of-band (e.g. a seed script or direct database action by an existing
operator), never through self-registration.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.user import UserRole
from app.schemas.technician import FieldOfficerResponse
from app.services.technician_service import TechnicianService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get(
    "/technicians/pending",
    response_model=list[FieldOfficerResponse],
    summary="List technicians awaiting approval (ADMIN only)",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
def list_pending_technicians(db: Session = Depends(get_db)) -> list[FieldOfficerResponse]:
    pending = TechnicianService(db).list_pending()
    return [FieldOfficerResponse.model_validate(fo) for fo in pending]
