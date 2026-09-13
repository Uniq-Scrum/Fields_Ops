"""
FastAPI authentication/authorization dependencies.

Two reusable pieces every protected route composes instead of
re-implementing:

- `get_current_user` — "who is calling": extracts the bearer token,
  validates it (app/core/security.py), then loads the User it names fresh
  from the database. The authenticated identity always comes from the
  validated token's `sub` claim, never from a user id supplied elsewhere in
  the request (body/query/header).
- `require_role` — "are they allowed": a dependency factory that layers a
  role check on top of `get_current_user`. The check always uses
  `current_user.role` as just loaded from the database — never a role
  claim taken directly from client input, and not even the token's own
  `role` claim, which is informational only.
"""
import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import InvalidTokenError, TokenExpiredError, decode_access_token
from app.models.user import ApprovalStatus, User, UserRole
from app.repositories.user_repository import UserRepository
from app.utils.exceptions import AccountNotAuthorizedError, ForbiddenError, UnauthorizedError

# `auto_error=False`: a missing token should produce the same
# UnauthorizedError (and JSON shape, via app/api/exception_handlers.py) as
# an invalid one, rather than FastAPI's own default 403. This endpoint's
# only purpose here is header extraction ("Authorization: Bearer <token>")
# and populating the OpenAPI security scheme for docs — see #26.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the authenticated User for the current request.

    JWT -> validate (signature, algorithm, expiration, required claims) ->
    extract subject -> load User by id -> reject if the user no longer
    exists or the account has been rejected -> return the User.

    A single indexed primary-key lookup per request (UserRepository.get_by_id
    -> Session.get, which also benefits from the identity map) — no extra
    queries, and never trusts the token's `role`/other claims as the final
    word on the user's current state.
    """
    if token is None:
        raise UnauthorizedError("Not authenticated")

    try:
        payload = decode_access_token(token)
    except (TokenExpiredError, InvalidTokenError):
        raise UnauthorizedError()

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise UnauthorizedError()

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        # The token is validly signed but names a user that no longer
        # exists (deleted after the token was issued) — reject, don't 500.
        raise UnauthorizedError()

    if user.approval_status == ApprovalStatus.REJECTED:
        raise AccountNotAuthorizedError()

    return user


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory: restrict a route to callers whose authenticated
    role is one of `allowed_roles`.

    Usage: `current_user: User = Depends(require_role(UserRole.ADMIN))`.

    Missing/invalid authentication still surfaces as 401 (from
    `get_current_user`, which runs first); an authenticated caller with the
    wrong role gets 403 — the two failure modes stay distinct.
    """

    def _check_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenError()
        return current_user

    return _check_role
