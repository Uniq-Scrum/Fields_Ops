"""Service-request submission and transaction handling."""
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.intake.intent import process_text_request
from app.models.service_request import ServiceRequest
from app.repositories.service_request_repository import ServiceRequestRepository


class ServiceRequestService:
    def __init__(self, db: Session):
        self._db = db
        self._requests = ServiceRequestRepository(db)

    def submit_text_request(self, request_text: str, customer_id: UUID) -> ServiceRequest:
        intake_state = process_text_request(
            request_text=request_text,
            customer_id=customer_id,
        )
        service_request = ServiceRequest(
            customer_id=intake_state["customer_id"],
            request_text=intake_state["request_text"],
            status=intake_state["status"].upper(),
        )

        try:
            self._requests.create(service_request)
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise

        return service_request