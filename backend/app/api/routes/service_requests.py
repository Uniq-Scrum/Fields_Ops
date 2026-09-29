"""Customer service-request intake endpoints."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.user import User, UserRole
from app.schemas.service_request import TextRepairRequest, TextRepairRequestResponse
from app.services.service_request_service import ServiceRequestService

router = APIRouter(prefix="/api/v1/service-requests", tags=["service-requests"])


@router.post(
    "",
    response_model=TextRepairRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a text repair request",
)
def submit_text_repair_request(
    payload: TextRepairRequest,
    current_user: User = Depends(require_role(UserRole.CUSTOMER)),
    db: Session = Depends(get_db),
) -> TextRepairRequestResponse:
    service_request = ServiceRequestService(db).submit_text_request(
        payload.request_text,
        customer_id=current_user.id,
    )
    return TextRepairRequestResponse(
        request_id=service_request.id,
        status=service_request.status.lower(),
    )
