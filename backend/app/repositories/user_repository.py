"""
User data-access layer.

Owns all direct SQLAlchemy access to the `users` table. Never commits or
rolls back the session itself — transaction boundaries belong to the
service layer, which may need to coordinate writes across more than one
repository (e.g. User + FieldOfficer) inside a single atomic operation.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self._db = db

    def create(self, user: User) -> User:
        """Stage a new user for insert. Flushes to surface IntegrityError early,
        without committing — the caller controls the transaction boundary."""
        self._db.add(user)
        self._db.flush()
        return user

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_by_phone(self, phone: str) -> User | None:
        stmt = select(User).where(User.phone == phone)
        return self._db.execute(stmt).scalar_one_or_none()
