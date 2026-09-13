"""
Custom exception types.

Keeping infrastructure errors (DB, cache, broker) as distinct types, rather
than letting raw driver exceptions bubble up, lets route handlers and
middleware catch them specifically and return clean, consistent error
responses without leaking internal details (connection strings, driver
tracebacks) to API consumers.
"""


class AppException(Exception):
    """Base class for all application-specific exceptions, if you don't already have one."""

    def __init__(self, message: str, *, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DatabaseConnectionError(AppException):
    """Raised when the database cannot be reached after all startup retries."""

    def __init__(self, message: str = "Database connection could not be established"):
        super().__init__(message, status_code=503)


class DatabaseTimeoutError(AppException):
    """Raised when a database operation exceeds its allotted time."""

    def __init__(self, message: str = "Database operation timed out"):
        super().__init__(message, status_code=504)


class ConflictError(AppException):
    """Raised when a request conflicts with existing state (e.g. a unique constraint)."""

    def __init__(self, message: str = "The request conflicts with existing data"):
        super().__init__(message, status_code=409)


class DuplicateUserError(ConflictError):
    """Raised when registration collides with an existing user's email/phone.

    Deliberately vague about which field collided — narrowing it down would
    let a caller enumerate which emails/phones are already registered.
    """

    def __init__(self, message: str = "A user with this email or phone already exists"):
        super().__init__(message)


class UnauthorizedError(AppException):
    """Raised when a request fails authentication (bad credentials, or a
    missing/invalid/expired token). Maps to HTTP 401."""

    def __init__(self, message: str = "Could not validate credentials"):
        super().__init__(message, status_code=401)


class InvalidCredentialsError(UnauthorizedError):
    """Raised on login with a wrong email or password.

    Deliberately identical whether the email doesn't exist or the password
    is wrong — distinguishing the two would let a caller enumerate
    registered emails. See `UserService.authenticate`.
    """

    def __init__(self, message: str = "Incorrect email or password"):
        super().__init__(message)


class ForbiddenError(AppException):
    """Raised when an authenticated caller lacks permission for the action
    they're attempting. Maps to HTTP 403 — distinct from UnauthorizedError's
    401, which means "we don't know who you are" rather than "we know who
    you are and it isn't enough"."""

    def __init__(self, message: str = "You do not have permission to perform this action"):
        super().__init__(message, status_code=403)


class AccountNotAuthorizedError(ForbiddenError):
    """Raised when an authenticated user's account is REJECTED — they proved
    who they are, but their account itself is not allowed access."""

    def __init__(self, message: str = "Account is not authorized to access this resource"):
        super().__init__(message)