"""
User business logic — registration, retrieval, and authentication.

This is the only layer that decides trust-sensitive defaults (role,
approval_status) and owns the transaction boundary for registration. Routes
call into this layer; they never touch the ORM or the session directly.
"""
import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.field_officer import FieldOfficer
from app.models.user import ApprovalStatus, User, UserRole
from app.repositories.technician_repository import TechnicianRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CustomerRegisterRequest, TechnicianRegisterRequest
from app.utils.exceptions import (
    AccountNotAuthorizedError,
    DuplicateUserError,
    InvalidCredentialsError,
)

logger = logging.getLogger(__name__)

# A precomputed bcrypt hash of a value nobody will ever type, used purely to
# keep `authenticate`'s runtime constant whether or not the email exists —
# without this, a "user not found" short-circuit would answer measurably
# faster than a real "wrong password" path, letting a caller enumerate
# registered emails by timing alone. Computed once at import time.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password-used-only-for-timing-safety")


class UserService:
    def __init__(self, db: Session):
        self._db = db
        self._users = UserRepository(db)
        self._technicians = TechnicianRepository(db)

    def register_customer(self, payload: CustomerRegisterRequest) -> User:
        """
        Create a new CUSTOMER account. Always APPROVED — a customer account
        is immediately usable, there is no vetting step for this role.

        Duplicate email/phone is handled by attempting the insert and
        catching the database's unique-constraint violation, not by a
        preceding SELECT — a check-then-insert is not safe under
        concurrent requests.
        """
        normalized_email = payload.email.strip().lower()

        user = User(
            name=payload.name,
            email=normalized_email,
            phone=payload.phone,
            password_hash=hash_password(payload.password),
            role=UserRole.CUSTOMER,
            approval_status=ApprovalStatus.APPROVED,
        )

        try:
            self._users.create(user)
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            logger.warning(
                "Customer registration rejected — duplicate email/phone (email=%s)",
                normalized_email,
            )
            raise DuplicateUserError() from exc

        logger.info("Customer registered (id=%s)", user.id)
        return user

    def register_technician(self, payload: TechnicianRegisterRequest) -> tuple[User, FieldOfficer]:
        """
        Create a new TECHNICIAN account together with its FieldOfficer
        profile, atomically. Both start PENDING — registering as a
        technician never grants dispatch-eligible/approved status by
        itself; that requires a separate admin-approval action.

        User and FieldOfficer are flushed inside the same transaction and
        committed exactly once: if either insert fails (including a
        duplicate email/phone), the whole transaction rolls back and
        neither row is left behind.
        """
        normalized_email = payload.email.strip().lower()

        user = User(
            name=payload.name,
            email=normalized_email,
            phone=payload.phone,
            password_hash=hash_password(payload.password),
            role=UserRole.TECHNICIAN,
            approval_status=ApprovalStatus.PENDING,
        )

        try:
            self._users.create(user)
            field_officer = FieldOfficer(
                user_id=user.id,
                skills=payload.skills,
                is_available=payload.is_available,
                approval_status=ApprovalStatus.PENDING,
            )
            self._technicians.create(field_officer)
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            logger.warning(
                "Technician registration rejected — duplicate email/phone (email=%s)",
                normalized_email,
            )
            raise DuplicateUserError() from exc

        logger.info("Technician registered (id=%s)", user.id)
        return user, field_officer

    def authenticate(self, email: str, password: str) -> User:
        """
        Verify credentials for login. Returns the authenticated User or
        raises:

        - InvalidCredentialsError (401) for an unknown email OR a wrong
          password — deliberately the same error either way, so a caller
          cannot use this endpoint to enumerate registered emails.
        - AccountNotAuthorizedError (403) if the credentials are correct
          but the account has been REJECTED.

        Never issues a token itself — that's the route's job, only after
        this returns successfully.
        """
        normalized_email = email.strip().lower()
        user = self._users.get_by_email(normalized_email)

        if user is None:
            # Still run a bcrypt verification against a dummy hash so this
            # branch costs the same wall-clock time as a real password
            # check — see _DUMMY_PASSWORD_HASH.
            verify_password(password, _DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError()

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        if user.approval_status == ApprovalStatus.REJECTED:
            raise AccountNotAuthorizedError()

        return user

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._users.get_by_id(user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._users.get_by_email(email.strip().lower())
