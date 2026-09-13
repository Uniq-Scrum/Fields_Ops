# Authentication & Authorization — Implementation Summary

A full production-grade authentication & authorization layer for FieldMind AI.
See [docs/AUTH.md](AUTH.md) for the complete design reference; this file is a
condensed summary of what was implemented and verified.

## Registration

- Split into two dedicated endpoints (no client-controlled `role` field on
  either): `POST /api/v1/auth/register` (customer, auto-approved) and
  `POST /api/v1/auth/register/technician` (pending approval, atomically
  creates the `FieldOfficer` row with skills/availability).
- Removed the ability to self-register as ADMIN entirely (previously
  possible via a client-supplied role value).
- Duplicate email/phone handled via DB unique constraints + `IntegrityError`
  catch, not check-then-insert — safe under concurrency.

## Password security

- Reused existing bcrypt/passlib hashing; added a timing-safe dummy-hash
  comparison in login so "unknown email" and "wrong password" take equal
  time (prevents enumeration).

## JWT

- `create_access_token` / `decode_access_token` in `core/security.py` using
  PyJWT, `HS256` only, explicit algorithm allow-list (blocks
  algorithm-confusion attacks), required-claims enforcement, configurable
  expiry.
- `JWT_SECRET_KEY` required with no default (fails startup if missing) plus
  an extra production-only guard against placeholder-looking secrets.

## Login

- `POST /api/v1/auth/login` — verifies credentials, rejects REJECTED
  accounts (403), allows PENDING accounts to still authenticate, issues a
  JWT on success.

## Authenticated context & RBAC

- `app/api/deps.py`: `get_current_user` (validates token, reloads user
  fresh from Postgres by PK) and `require_role(...)` (checks the
  DB-loaded role, never a client- or token-supplied one).
- Filled in the previously-empty `users.py` / `technicians.py` / `admin.py`
  route stubs with minimal RBAC-gated example endpoints and wired them
  into `main.py`.

## Testing & validation

- 106 tests passing (added ~41 new: JWT unit tests, login/`/me`
  integration tests, full RBAC matrix, atomicity/rollback checks,
  timing/enumeration/secret-leak security tests).
- Manually verified the live server end-to-end (register → login →
  protected routes → 401/403 cases) and confirmed `alembic` is at head
  with no drift.
- `docs/AUTH.md` documents the whole design, including why registration
  was split into two endpoints.

## Status

Registration, login, JWT issuance/validation, RBAC, and protected routes
are all implemented, tested, and manually verified — the full task
checklist has been worked through. Nothing has been committed to git yet —
all changes are in the working tree, awaiting review/commit instruction.
