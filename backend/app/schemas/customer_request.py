from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


class Location(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Latitude must be between -90 and 90")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude must be between -180 and 180")
    address: Optional[str] = Field(None, max_length=500, description="Optional text address")


class CustomerRequestPayload(BaseModel):
    """
    Schema for customer intake request supporting multi-modal input (text or audio).
    Validates that at least one form of input is provided and that location data is valid.
    """

    text_input: Optional[str] = Field(
        None,
        min_length=1,
        max_length=2000,
        description="Text description of the issue"
    )
    audio_url: Optional[HttpUrl] = Field(
        None,
        description="URL to the audio/voice message"
    )
    location: Optional[Location] = Field(
        None,
        description="Location coordinates of the customer"
    )

    @model_validator(mode='after')
    def validate_content_presence(self) -> "CustomerRequestPayload":
        """Ensure either text_input or audio_url is provided and valid."""
        if not self.text_input and not self.audio_url:
            raise ValueError("Either text_input or audio_url must be provided.")
        
        if self.text_input is not None and not self.text_input.strip():
            raise ValueError("text_input must not be blank.")
            
        return self


class CustomerRequestResponse(BaseModel):
    """Response returned upon successful validation of the request."""
    request_id: str
    status: str
