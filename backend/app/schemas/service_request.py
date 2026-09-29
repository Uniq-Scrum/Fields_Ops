"""Schemas for customer-submitted text repair requests."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TextRepairRequest(BaseModel):
    """Natural-language description submitted by a customer."""

    request_text: str = Field(min_length=1, max_length=2000)

    @field_validator("request_text")
    @classmethod
    def _strip_and_reject_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("request_text must not be blank")
        return value


class TextRepairRequestResponse(BaseModel):
    """Acknowledgment returned after text reaches the intake flow."""

    request_id: UUID
    status: Literal["received"]
