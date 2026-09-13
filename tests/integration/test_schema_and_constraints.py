"""
Verifies the Alembic-migrated schema itself: tables, enum types, unique/
foreign-key constraints, and that PostgreSQL — not just the application —
rejects invalid data. These exercise the live database directly (raw SQL/
inspector), independent of the ORM layer.
"""
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError

from app.core.database import engine


@pytest.fixture()
def raw_connection():
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def test_users_table_exists_with_expected_columns():
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("users")}
    assert columns == {
        "id",
        "name",
        "email",
        "phone",
        "password_hash",
        "role",
        "approval_status",
        "created_at",
        "updated_at",
    }


def test_field_officers_table_exists_with_expected_columns():
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("field_officers")}
    assert columns == {
        "id",
        "user_id",
        "skills",
        "is_available",
        "approval_status",
        "created_at",
        "updated_at",
    }


def test_field_officers_user_id_has_foreign_key_and_unique_constraint():
    inspector = inspect(engine)
    fks = inspector.get_foreign_keys("field_officers")
    assert any(
        fk["referred_table"] == "users" and fk["constrained_columns"] == ["user_id"]
        for fk in fks
    )

    unique_constraints = inspector.get_unique_constraints("field_officers")
    assert any(uc["column_names"] == ["user_id"] for uc in unique_constraints)


def test_users_email_and_phone_are_unique():
    inspector = inspect(engine)
    unique_columns = {
        tuple(uc["column_names"]) for uc in inspector.get_unique_constraints("users")
    }
    assert ("email",) in unique_columns
    assert ("phone",) in unique_columns


def test_user_role_enum_rejects_invalid_value_at_database_level(raw_connection):
    with pytest.raises((DataError, IntegrityError, Exception)):
        raw_connection.execute(
            text(
                """
                INSERT INTO users (id, name, email, phone, password_hash, role, approval_status)
                VALUES (:id, 'X', :email, :phone, 'hash', 'SUPERADMIN', 'PENDING')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "email": f"invalid.{uuid.uuid4().hex}@example.com",
                "phone": f"+1{uuid.uuid4().int % 10**10:010d}",
            },
        )


def test_field_officer_requires_existing_user(raw_connection):
    with pytest.raises(IntegrityError):
        raw_connection.execute(
            text(
                """
                INSERT INTO field_officers (id, user_id, skills, is_available, approval_status)
                VALUES (:id, :user_id, '{}', false, 'PENDING')
                """
            ),
            {"id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
        )


def test_users_updated_at_trigger_exists():
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = 'users'::regclass "
                "AND NOT tgisinternal"
            )
        ).scalars().all()
    assert "trg_users_set_updated_at" in result


def test_alembic_is_at_head():
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "e2702f96a61d"
