"""The single permission map (ADR 0013). Routes check a permission; services still check object ownership."""

from typing import Final

ROLES: Final = ("user", "business", "staff", "admin", "superadmin")

PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "user": frozenset({"post:write", "booking:create", "order:create", "business:create"}),
    "business": frozenset(
        {"post:write", "booking:create", "order:create", "business:create", "business:manage", "booking:manage", "shop:manage"}
    ),
    "staff": frozenset({"ticket:resolve", "ticket:escalate", "report:review"}),
    "admin": frozenset(
        {"report:review", "report:remove", "ad:approve", "verify:grant", "ticket:resolve", "audit:read", "user:read"}
    ),
    "superadmin": frozenset({"*"}),
}

# Roles that must use MFA once TOTP/passkeys ship (Blueprint 12.1).
PRIVILEGED_ROLES: Final = frozenset({"staff", "admin", "superadmin"})


def has_permission(role: str, permission: str) -> bool:
    allowed = PERMISSIONS.get(role, frozenset())
    return "*" in allowed or permission in allowed
