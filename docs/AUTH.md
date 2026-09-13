# Authentication & Authorization

Covers registration, password hashing, JWT issuance/validation, and
role-based access control (RBAC). See [docs/DATABASE.md](DATABASE.md) for
general PostgreSQL setup and [docs/ARCHITECTURE.md](ARCHITECTURE.md) for
the overall layering (route → schema → service → repository → model → DB).

## Layering

```
app/api/routes/auth.py          HTTP only: register/login/me — calls UserService + core.security
app/api/routes/users.py         GET /users/me — any authenticated role
app/api/routes/technicians.py   GET /technicians/me — TECHNICIAN only
app/api/routes/admin.py         GET /admin/technicians/pending — ADMIN only
app/api/deps.py                 get_current_user, require_role — the auth/RBAC dependencies every protected route uses
app/schemas/auth.py             CustomerRegisterRequest, TechnicianRegisterRequest, LoginRequest, TokenResponse
app/schemas/user.py             UserResponse — the only shape a User is ever serialized to
app/schemas/technician.py       FieldOfficerResponse — the only shape a FieldOfficer is ever serialized to
app/services/user_service.py    Business rules, registration transaction boundary, authenticate()
app/services/technician_service.py  FieldOfficer lookups (own profile, pending list)
app/repositories/user_repository.py       User data access (no commits)
app/repositories/technician_repository.py FieldOfficer data access (no commits)
app/models/user.py               User ORM model, UserRole + ApprovalStatus enums
app/models/field_officer.py     FieldOfficer ORM model (technician profile)
app/core/security.py             Password hashing (bcrypt) + JWT issuance/validation (PyJWT)
app/core/config.py               JWT_SECRET_KEY / JWT_ALGORITHM / JWT_ACCESS_TOKEN_EXPIRE_MINUTES
app/api/exception_handlers.py   Translates AppException -> HTTP responses; never
                                  leaks raw SQLAlchemy/psycopg2/JWT errors to a client
```

## Request flow

```
Registration:  API -> Pydantic schema -> UserService -> Repository -> SQLAlchemy -> PostgreSQL
Login:         API -> UserService.authenticate -> core.security.create_access_token -> TokenResponse
Protected API: Client (Bearer token)
                 -> app/api/deps.py:get_current_user
                    -> core.security.decode_access_token (signature, algorithm, expiry, claims)
                    -> UserRepository.get_by_id (fresh load, PK lookup)
                    -> reject if missing / REJECTED
                 -> app/api/deps.py:require_role(...) (uses current_user.role, never a client- or
                    token-claim-supplied role, as the final authorization decision)
                 -> route handler -> service -> repository -> PostgreSQL
```

## User model (`app/models/user.py`)

Unchanged by this work — see the table in git history / ARCHITECTURE.md.
`UserRole` = `CUSTOMER` \| `TECHNICIAN` \| `ADMIN`. `ApprovalStatus` =
`PENDING` \| `APPROVED` \| `REJECTED`, used on both `users` (account-level)
and `field_officers` (technician-vetting level).

## Registration APIs

There is **no single "generic" registration endpoint that takes a `role`
field.** Each role has its own endpoint with its own schema, so a client
can never choose an elevated role by sending an arbitrary value — the
field simply doesn't exist on the request.

### `POST /api/v1/auth/register` — customer registration

Always creates a `CUSTOMER`, immediately `APPROVED`.

```json
// Request (CustomerRegisterRequest)
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "phone": "+14155550123",
  "password": "Str0ng!Pass1"
}
```

Response `201 Created` (`UserResponse`) — no `role`/`approval_status`
override possible; no `password`/`password_hash` in the response.

### `POST /api/v1/auth/register/technician` — technician registration

Always creates a `TECHNICIAN`, `PENDING` approval, **and** atomically
creates the matching `FieldOfficer` row (also `PENDING`) in the same
transaction (`UserService.register_technician`). If either insert fails
(including a duplicate email/phone), the whole transaction rolls back —
there is no code path that leaves an orphan `User` or `FieldOfficer`.

```json
// Request (TechnicianRegisterRequest)
{
  "name": "Tom Tech",
  "email": "tom@example.com",
  "phone": "+14155550199",
  "password": "Str0ng!Pass1",
  "skills": ["electrical", "plumbing"],
  "is_available": true
}
```

Response `201 Created` (`TechnicianRegisterResponse` — `UserResponse` plus
`skills` / `is_available` / `field_officer_approval_status`).

**Neither schema has an `approval_status`, `role`, or any other
elevation/self-approval field.** Sending one in the JSON body is silently
ignored (Pydantic's default `extra="ignore"`) — it has no effect on the
resulting role or approval state, which are hardcoded in
`UserService.register_customer` / `register_technician`.

There is intentionally **no public `ADMIN` self-registration endpoint.**
Admin accounts are provisioned out-of-band (a seed script or direct action
by an existing operator) — see `app/api/routes/admin.py`'s module
docstring. This is a deliberate hardening decision beyond what the prior
single-endpoint design allowed (see "Design history" below).

Errors: `409 Conflict` on duplicate email/phone (generic message —
deliberately doesn't say which field collided, to prevent enumeration),
`422 Unprocessable Entity` on any Pydantic validation failure.

### Registration & concurrency

Duplicate detection does **not** do a `SELECT` pre-check followed by an
`INSERT`. Instead, the service inserts directly and relies on the
database's `UNIQUE` constraints on `email`/`phone`; a violation raises
`sqlalchemy.exc.IntegrityError`, caught and translated to
`DuplicateUserError` (409). Postgres — not application code — is the
single arbiter of uniqueness, so this is safe under arbitrary concurrency.

## Password hashing (`app/core/security.py`)

Unchanged: `hash_password` / `verify_password`, bcrypt via passlib's
`CryptContext`, fails closed (`False`, never raises) on a malformed stored
hash. `UserService.authenticate` additionally verifies against a
precomputed dummy hash when the email doesn't exist at all, so a
"nonexistent email" response takes the same wall-clock time as a "wrong
password" response — this endpoint cannot be used to enumerate registered
emails by timing.

## Login (`POST /api/v1/auth/login`)

```json
// Request (LoginRequest)
{ "email": "jane@example.com", "password": "Str0ng!Pass1" }
```

Flow (`UserService.authenticate`, `app/api/routes/auth.py:login`):

```
find user by email (indexed lookup)
  -> not found: verify against dummy hash anyway, then 401 (generic message)
  -> found: verify_password
       -> wrong: 401 (same generic message as "not found")
       -> correct:
            -> approval_status == REJECTED: 403 "Account is not authorized..."
            -> otherwise: issue JWT, return TokenResponse
```

`PENDING` accounts (freshly-registered technicians, or any admin-created
account awaiting review) **can still log in** — this lets them check their
own status via `GET /api/v1/auth/me` or `GET /api/v1/technicians/me`.
Approval only gates capability, not authentication itself. Only
`REJECTED` blocks login outright.

Response `200 OK` (`TokenResponse`):

```json
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 1800 }
```

## JWT (`app/core/security.py`)

- Library: [PyJWT](https://pyjwt.readthedocs.io/), pinned in
  `requirements.txt`.
- Algorithm: `HS256` (configurable via `JWT_ALGORITHM`, but constrained to
  a closed `Literal["HS256"]` set in `Settings` — not a free-form string a
  misconfigured environment could widen).
- Claims: `sub` (user id, string), `role` (UserRole value, informational
  only — see below), `type` ("access"), `iat`, `exp`. **Nothing else** —
  no password, no password hash, no other PII.
- Expiration: configurable via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default
  30 minutes).
- Verification (`decode_access_token`) passes `algorithms=[settings.JWT_ALGORITHM]`
  explicitly — never derived from the token's own header — which is what
  actually prevents an algorithm-confusion attack (e.g. a forged
  `alg=none` token). Required claims (`exp`, `iat`, `sub`, `role`) are
  enforced via `options={"require": [...]}`. A `type` claim other than
  `"access"` is rejected, so a future refresh-token type (not implemented
  yet) could never be replayed as an access token.
- All JWT errors (expired, malformed, bad signature, wrong algorithm,
  missing claims) are caught and re-raised as `TokenExpiredError` /
  `InvalidTokenError` — a raw `jwt.PyJWTError` (whose message can include
  internal parsing detail) never escapes this module.

**The `role` claim inside the token is informational only.** Every
authorization decision (`require_role` in `app/api/deps.py`) uses
`current_user.role` as freshly loaded from the database by
`get_current_user` on that request — never the token's own `role` claim.
This means a role change (or an account being rejected) takes effect on
the very next request, without waiting for the token to expire.

## JWT secret & config (`app/core/config.py`)

```
JWT_SECRET_KEY                    required, no default, min 32 chars (Settings fails to
                                   construct without it — same posture as POSTGRES_PASSWORD)
JWT_ALGORITHM                     default "HS256", constrained to that one value
JWT_ACCESS_TOKEN_EXPIRE_MINUTES   default 30
```

- Never hardcoded, never committed: sourced from the environment /
  `.env` via the existing `Settings` class.
- `.env.example` ships a clearly-labeled placeholder
  (`changeme-generate-a-long-random-secret-of-at-least-32-characters`) —
  copy `.env.example` to `.env` and replace it, e.g.:
  `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- A `model_validator` on `Settings` additionally rejects a secret
  containing an obvious placeholder marker ("changeme", "example",
  "secret-key", etc.) **specifically when `ENVIRONMENT=production`** —
  the app fails to start rather than run production signed with a
  guessable key. Local/staging are unaffected by this extra check (they
  still get the unconditional 32-character minimum).

## Authenticated user context & RBAC (`app/api/deps.py`)

- `get_current_user`: extracts the `Authorization: Bearer <token>` header,
  validates it via `decode_access_token`, loads the `User` named by the
  token's `sub` claim (a single indexed primary-key lookup —
  `UserRepository.get_by_id`), and rejects (401) if the token is
  missing/invalid/expired or the user no longer exists, or (403) if the
  account is `REJECTED`. The authenticated identity always comes from the
  validated token — never from a user id supplied elsewhere in the request.
- `require_role(*roles)`: a dependency factory layering a role check on
  top of `get_current_user`. An authorization decision always uses
  `current_user.role` as just loaded from the database. A client cannot
  influence this via the request body, query params, headers, or even the
  token's own `role` claim (which is not consulted here).
- **401 vs 403**: missing/invalid/expired authentication is always 401
  ("who are you?"); a recognized, authenticated caller whose role doesn't
  match is always 403 ("I know who you are, and it isn't enough"). Both
  are `AppException` subclasses (`UnauthorizedError`, `ForbiddenError` —
  `app/utils/exceptions.py`), routed through the existing
  `app/api/exception_handlers.py` so no raw exception ever reaches a
  client.

## Protected routes (RBAC demonstration/seed endpoints)

| Route | Auth | Notes |
|---|---|---|
| `POST /api/v1/auth/register` | Public | Customer registration |
| `POST /api/v1/auth/register/technician` | Public | Technician registration |
| `POST /api/v1/auth/login` | Public | Issues a JWT |
| `GET /api/v1/auth/me` | Any authenticated role | Caller's own profile |
| `GET /api/v1/users/me` | Any authenticated role | Same shape, owned by the users surface |
| `GET /api/v1/technicians/me` | `TECHNICIAN` only | Caller's own FieldOfficer profile (accessible even while `PENDING`) |
| `GET /api/v1/admin/technicians/pending` | `ADMIN` only | Read-only list of FieldOfficers awaiting approval |
| `GET /health`, `/health/*` | Public | Liveness/readiness probes |

`users.py` / `technicians.py` / `admin.py` previously existed as empty
placeholder routers, unwired, reserved for their respective feature teams.
This work adds only the minimal endpoints above — enough to exercise and
test authentication and RBAC end-to-end — and wires all three routers into
`app/main.py`. Business functionality for those surfaces (user management,
technician discovery/dispatch, the actual approve/reject action) remains
out of scope and unimplemented, left for those teams.

## Design history: why registration is two endpoints, not one

The pre-existing `POST /api/v1/auth/register` accepted a client-supplied
`role: UserRole` field (`CUSTOMER` / `TECHNICIAN` / `ADMIN`), defaulting
non-`CUSTOMER` roles to `PENDING` approval. While that already prevented
self-approval, it still let any anonymous caller create a `PENDING` ADMIN
account and gave technicians no way to submit `skills`/`is_available` at
signup. This work splits registration into a dedicated endpoint per role
with its own schema (no shared `role` field to send at all), removes
public ADMIN self-registration entirely, and adds technician-specific
fields to the technician flow — closing a privilege-escalation-adjacent
surface without changing customer registration's external behavior.

## Migrations

No new Alembic migrations were required: JWT is stateless (no new table),
and `field_officers.skills` / `is_available` / `approval_status` already
existed for the technician registration flow to populate. See the two
existing revisions under `backend/alembic/versions/` (unchanged).

## Environment requirements

In addition to the existing `POSTGRES_*` variables, both the repository
root `.env` and `backend/.env` must define `JWT_SECRET_KEY` (see above) —
the application fails to start otherwise. `JWT_ALGORITHM` and
`JWT_ACCESS_TOKEN_EXPIRE_MINUTES` have sane defaults and are optional.

## Testing

```
# from the repository root, with backend/.venv activated
pip install -r backend/requirements.txt
python -m pytest tests/ -v
```

- `tests/unit/` — schema validation (`test_auth_schemas.py`), password
  hashing (`test_security.py`), and JWT creation/validation in isolation,
  no DB (`test_jwt.py`).
- `tests/integration/` — full registration APIs
  (`test_registration_api.py`), login + `/auth/me`
  (`test_auth_login_api.py`), RBAC across all three protected example
  routes (`test_rbac_api.py`), and schema/constraint checks
  (`test_schema_and_constraints.py`) — all against a real PostgreSQL
  database (`docker compose up -d postgres`, migrated to head).
- `tests/security/` — plaintext-password-never-persisted,
  response-never-leaks-password/secret checks, login timing/enumeration
  behavior, and JWT payload content checks
  (`test_password_storage.py`).

Every DB-backed test runs inside its own outer transaction + `SAVEPOINT`
(`tests/conftest.py`) — the test's final rollback discards everything it
wrote. `tests/conftest.py` also provides two fixtures used throughout the
new tests:

- `make_user(role=..., approval_status=..., password=...)` — creates a
  `User` directly via the ORM, for roles/states no public API can produce
  (e.g. `ADMIN`, or a `REJECTED` account).
- `auth_headers(email, password)` — logs in through the real
  `POST /api/v1/auth/login` endpoint and returns an `Authorization` header
  dict, so RBAC tests exercise genuine end-to-end token issuance and
  validation rather than a hand-fabricated token.
