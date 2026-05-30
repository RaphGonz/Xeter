# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
DAL base: MissingTenantError and the require_tenant() guard function.

Every repository method that touches tenant-scoped data must call
require_tenant(tenant_id) as its first line. This raises BEFORE any
database interaction — it is a Python-boundary enforcement, not a
database-level check. PostgreSQL RLS is defence-in-depth only.

Usage::

    from xeter.shared.dal.base import require_tenant, MissingTenantError

    class MyRepository:
        async def get(self, record_id: str, tenant_id: str | None) -> ...:
            require_tenant(tenant_id)   # raises MissingTenantError if absent
            ...
"""


class MissingTenantError(RuntimeError):
    """Raised when a DAL method is called without a valid tenant_id.

    This is a programming error, not a user-facing error. Callers must
    always supply a non-empty, non-whitespace tenant_id for any
    tenant-scoped repository operation.
    """


def require_tenant(tenant_id: str | None) -> str:
    """Validate that tenant_id is present and non-empty.

    Strips surrounding whitespace before checking. Raises MissingTenantError
    if the value is None, empty, or whitespace-only. Returns the original
    (unstripped) value so callers can pass it directly to queries.

    Args:
        tenant_id: The tenant identifier to validate.

    Returns:
        The tenant_id value unchanged (not stripped, preserves original).

    Raises:
        MissingTenantError: If tenant_id is None, empty, or whitespace-only.
    """
    if tenant_id is None or not str(tenant_id).strip():
        raise MissingTenantError(
            "tenant_id is required but was not provided or is empty. "
            "All DAL operations on tenant-scoped data require a valid tenant_id."
        )
    return tenant_id
