"""Persisted customer service-request model."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ServiceRequest(Base):
	"""A text repair request submitted by an authenticated customer."""

	__tablename__ = "service_requests"
	__table_args__ = (
		Index("ix_service_requests_customer_created_at", "customer_id", "created_at"),
	)

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True),
		primary_key=True,
		default=uuid.uuid4,
		server_default=text("gen_random_uuid()"),
	)
	customer_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
	)
	request_text: Mapped[str] = mapped_column(String(2000), nullable=False)
	status: Mapped[str] = mapped_column(
		String(32), nullable=False, default="RECEIVED", server_default="RECEIVED"
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
