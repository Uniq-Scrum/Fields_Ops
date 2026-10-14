from uuid import uuid4

from fastapi import APIRouter, status

from app.schemas.service_request import ServiceRequestCreate, ServiceRequestResponse

router = APIRouter(prefix="/api/service-requests", tags=["service requests"])


@router.post(
    "",
    response_model=ServiceRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive a customer service request",
)
def create_service_request(payload: ServiceRequestCreate) -> ServiceRequestResponse:
    return ServiceRequestResponse(
        job_id=str(uuid4()),
        status="received",
        message="Your request was received.",
    )
