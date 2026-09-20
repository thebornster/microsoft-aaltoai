"""Fail-closed secret loading (gate 5: "remove unsafe-looking defaults from
the normal path").

Insecure demo defaults (a fixed HMAC key, a fixed approval-page secret) only
ever apply when RAJA_DEMO_MODE=1 is set explicitly. Outside demo mode, a
missing required secret is a startup error, not a silent fallback to a
well-known value — the whole point being that nothing in the normal
(non-demo) path can look secure while actually running on a public default.
"""
import os


class ConfigError(RuntimeError):
    pass


def is_demo_mode() -> bool:
    return os.environ.get("RAJA_DEMO_MODE") == "1"


def approval_ttl_seconds() -> int:
    default = 30 * 60 if is_demo_mode() else 5 * 60
    try:
        return max(1, int(os.environ.get("RAJA_APPROVAL_TTL_SECONDS", default)))
    except ValueError as exc:
        raise ConfigError("RAJA_APPROVAL_TTL_SECONDS must be an integer") from exc


def public_approval_links() -> bool:
    """Whether generated demo links carry the configured approval secret."""
    return os.environ.get("RAJA_PUBLIC_APPROVAL_LINKS") == "1"


def require_secret(env_var: str, demo_default: str) -> str:
    """Return os.environ[env_var], or demo_default only under RAJA_DEMO_MODE=1.

    Raises ConfigError (fail closed) if env_var is unset/empty and demo mode
    is not explicitly enabled.
    """
    value = os.environ.get(env_var)
    if value:
        return value
    if is_demo_mode():
        return demo_default
    raise ConfigError(
        f"{env_var} is required unless RAJA_DEMO_MODE=1 is set explicitly "
        f"(fail-closed: no insecure default is used outside demo mode)"
    )
