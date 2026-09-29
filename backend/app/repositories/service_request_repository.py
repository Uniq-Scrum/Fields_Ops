"""Data-access layer for customer service requests."""
from sqlalchemy.orm import Session

from app.models.service_request import ServiceRequest


class ServiceRequestRepository:
	def __init__(self, db: Session):
		self._db = db

	def create(self, service_request: ServiceRequest) -> ServiceRequest:
		self._db.add(service_request)
		self._db.flush()
		return service_request
