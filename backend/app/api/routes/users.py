"""
User-facing routes.

Currently exposes only the authenticated caller's own profile — an
authenticated-but-role-agnostic endpoint that exercises `get_current_user`
independent of any RBAC restriction. Broader user management (list/update
other users, etc.) belongs to whichever team owns that surface and is not
implemented here.
"""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the authenticated user's own profile (any role)",
)
def read_own_profile(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
