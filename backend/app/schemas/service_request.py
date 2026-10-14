from pydantic import BaseModel, Field, field_validator


class ServiceRequestCreate(BaseModel):
    """Customer-provided description for an initial service request."""

    user_prompt: str = Field(min_length=1, max_length=1000)

    @field_validator("user_prompt")
    @classmethod
    def validate_user_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Describe the problem before submitting.")
        if not any(character.isalpha() for character in normalized):
            raise ValueError("Add a few words describing the repair.")
        return normalized


class ServiceRequestResponse(BaseModel):
    """Acknowledgement returned after the request reaches the API."""

    job_id: str
    status: str
    message: str
