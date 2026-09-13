"""Application-wide constants shared across layers."""

# --- Password policy (enforced in backend/app/schemas/auth.py) ---
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# --- Technician profile (enforced in backend/app/schemas/auth.py) ---
# SKILL_MAX_LENGTH matches the column width of field_officers.skills
# (ARRAY(String(100)) — see app/models/field_officer.py) so a rejection
# happens at request-validation time, not as a database-level truncation
# or error deep inside the registration transaction.
SKILL_MAX_LENGTH = 100
MAX_SKILLS_PER_TECHNICIAN = 50
