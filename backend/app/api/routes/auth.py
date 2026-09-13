"""
Authentication routes.

Thin HTTP layer only: request validation is Pydantic's job (the
`*RegisterRequest`/`LoginRequest` schemas), business rules and the
transaction boundary belong to `UserService`, and JWT issuance/validation
belongs to `app/core/security.py`. This module never touches the ORM, the
database session, or a signing key beyond handing the session to the
service and the resulting user to `create_access_token`.

Public endpoints: register (both flows) and login. `/me` requires a valid
token but no particular role — any authenticated user may read their own
identity.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import (
    CustomerRegisterRequest,
    LoginRequest,
    TechnicianRegisterRequest,
    TechnicianRegisterResponse,
    TokenResponse,
)
from app.schemas.user import UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
)
def register_customer(payload: CustomerRegisterRequest, db: Session = Depends(get_db)) -> UserResponse:
    user = UserService(db).register_customer(payload)
    return UserResponse.model_validate(user)


@router.post(
    "/register/technician",
    response_model=TechnicianRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new technician account (requires admin approval before use)",
)
def register_technician(
    payload: TechnicianRegisterRequest, db: Session = Depends(get_db)
) -> TechnicianRegisterResponse:
    user, field_officer = UserService(db).register_technician(payload)
    return TechnicianRegisterResponse(
        **UserResponse.model_validate(user).model_dump(),
        skills=field_officer.skills,
        is_available=field_officer.is_available,
        field_officer_approval_status=field_officer.approval_status,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate with email/password and obtain a JWT access token",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = UserService(db).authenticate(payload.email, payload.password)
    access_token = create_access_token(subject=str(user.id), role=user.role.value)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the authenticated caller's own profile",
)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
