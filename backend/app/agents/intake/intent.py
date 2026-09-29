"""Initial handoff for customer-submitted text repair requests."""
from typing import Literal, TypedDict
from uuid import UUID


class TextRequestIntakeState(TypedDict):
	customer_id: UUID
	request_text: str
	status: Literal["received"]


def process_text_request(
	*, request_text: str, customer_id: UUID
) -> TextRequestIntakeState:
	"""Create the intake state consumed by subsequent request-processing steps."""
	return {
		"customer_id": customer_id,
		"request_text": request_text,
		"status": "received",
	}
