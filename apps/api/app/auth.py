from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional, Set

from fastapi import Header, HTTPException


ALL_ROLES = {"support_agent", "approver", "knowledge_admin", "admin"}
TICKET_READ_ROLES = {"support_agent", "admin"}
TRACE_READ_ROLES = {"support_agent", "approver", "admin"}
RUN_ROLES = {"support_agent", "admin"}
APPROVAL_READ_ROLES = {"approver", "admin"}
APPROVAL_DECISION_ROLES = {"approver", "admin"}
KNOWLEDGE_READ_ROLES = {"knowledge_admin", "admin"}
KNOWLEDGE_WRITE_ROLES = {"knowledge_admin", "admin"}
ADMIN_ROLES = {"admin"}
READ_ROLES = TICKET_READ_ROLES

LOCAL_AUTH_ENVS = {"development", "dev", "local", "test"}
PRODUCTION_LIKE_ENVS = {"production", "staging", "preview"}


@dataclass(frozen=True)
class Principal:
    email: str
    tenant_id: str
    tenant_ids: Set[str]
    roles: Set[str]
    auth_source: str

    def can_access_tenant(self, tenant_id: str) -> bool:
        return tenant_id in self.tenant_ids

    def has_any_role(self, allowed_roles: Iterable[str]) -> bool:
        return bool(self.roles.intersection(allowed_roles))

    def as_response(self) -> dict:
        return {
            "email": self.email,
            "tenant_id": self.tenant_id,
            "tenant_ids": sorted(self.tenant_ids),
            "roles": sorted(self.roles),
            "auth_source": self.auth_source,
        }


def _split_header(value: Optional[str], *, lower: bool = False) -> Set[str]:
    if not value:
        return set()
    items = {item.strip() for item in value.split(",") if item.strip()}
    if lower:
        return {item.lower() for item in items}
    return items


def _first_header(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def _app_env() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").lower()


def _auth_mode() -> str:
    configured = os.getenv("SUPPORT_COPILOT_AUTH_MODE")
    if configured:
        return configured.lower()
    return "trusted_headers" if _app_env() in PRODUCTION_LIKE_ENVS else "local_headers"


def _local_headers_allowed() -> bool:
    return _app_env() in LOCAL_AUTH_ENVS


def _trusted_identity_secret() -> Optional[str]:
    secret = os.getenv("SUPPORT_COPILOT_TRUSTED_IDENTITY_SECRET")
    return secret.strip() if secret and secret.strip() else None


def _require_trusted_identity(presented_secret: Optional[str]) -> None:
    expected_secret = _trusted_identity_secret()
    if not expected_secret:
        raise HTTPException(status_code=401, detail="Trusted identity context is not configured")
    if not presented_secret or presented_secret.strip() != expected_secret:
        raise HTTPException(status_code=401, detail="Trusted identity context is required")


def auth_status_from_env() -> dict:
    mode = _auth_mode()
    return {
        "mode": mode,
        "app_env": _app_env(),
        "trusted_identity_required": mode == "trusted_headers",
        "trusted_identity_secret_configured": bool(_trusted_identity_secret()),
        "local_dev_headers_enabled": mode == "local_headers" and _local_headers_allowed(),
    }


def _principal_from_headers(
    *,
    email: Optional[str],
    tenant_id: Optional[str],
    user_roles: Optional[str],
    tenant_ids: Optional[str],
    auth_source: str,
) -> Principal:
    if not email or not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication headers are required")

    roles = _split_header(user_roles, lower=True).intersection(ALL_ROLES)
    if not roles:
        raise HTTPException(status_code=403, detail="At least one recognized user role is required")

    active_tenant_id = tenant_id.strip()
    scoped_tenant_ids = _split_header(tenant_ids) or {active_tenant_id}
    if active_tenant_id not in scoped_tenant_ids:
        raise HTTPException(status_code=403, detail="Active tenant is outside the authenticated tenant scope")

    return Principal(
        email=email.strip(),
        tenant_id=active_tenant_id,
        tenant_ids=scoped_tenant_ids,
        roles=roles,
        auth_source=auth_source,
    )


def get_current_principal(
    user_email: Optional[str] = Header(default=None, alias="X-User-Email"),
    tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
    user_roles: Optional[str] = Header(default=None, alias="X-User-Roles"),
    tenant_ids: Optional[str] = Header(default=None, alias="X-Tenant-Ids"),
    trusted_identity: Optional[str] = Header(default=None, alias="X-Support-Copilot-Trusted-Identity"),
    trusted_user_email: Optional[str] = Header(default=None, alias="X-Support-Copilot-User-Email"),
    trusted_tenant_id: Optional[str] = Header(default=None, alias="X-Support-Copilot-Tenant-Id"),
    trusted_user_roles: Optional[str] = Header(default=None, alias="X-Support-Copilot-User-Roles"),
    trusted_tenant_ids: Optional[str] = Header(default=None, alias="X-Support-Copilot-Tenant-Ids"),
    auth_request_email: Optional[str] = Header(default=None, alias="X-Auth-Request-Email"),
    auth_request_tenant_id: Optional[str] = Header(default=None, alias="X-Auth-Request-Tenant-Id"),
    auth_request_tenant_ids: Optional[str] = Header(default=None, alias="X-Auth-Request-Tenant-Ids"),
    auth_request_roles: Optional[str] = Header(default=None, alias="X-Auth-Request-Roles"),
    auth_request_groups: Optional[str] = Header(default=None, alias="X-Auth-Request-Groups"),
) -> Principal:
    mode = _auth_mode()

    if mode == "local_headers":
        if not _local_headers_allowed():
            raise HTTPException(status_code=401, detail="Local identity headers are disabled outside local development")
        return _principal_from_headers(
            email=user_email,
            tenant_id=tenant_id,
            user_roles=user_roles,
            tenant_ids=tenant_ids,
            auth_source="local_dev_headers",
        )

    if mode != "trusted_headers":
        raise HTTPException(status_code=500, detail=f"Unsupported auth mode: {mode}")

    _require_trusted_identity(trusted_identity)
    return _principal_from_headers(
        email=_first_header(trusted_user_email, auth_request_email, user_email),
        tenant_id=_first_header(trusted_tenant_id, auth_request_tenant_id, tenant_id),
        user_roles=_first_header(trusted_user_roles, auth_request_roles, auth_request_groups, user_roles),
        tenant_ids=_first_header(trusted_tenant_ids, auth_request_tenant_ids, tenant_ids),
        auth_source="trusted_headers",
    )


def require_role(principal: Principal, allowed_roles: Iterable[str], detail: str) -> None:
    if not principal.has_any_role(allowed_roles):
        raise HTTPException(status_code=403, detail=detail)


def require_tenant_access(principal: Principal, tenant_id: str, *, hide: bool = False) -> None:
    if principal.can_access_tenant(tenant_id):
        return
    if hide:
        raise HTTPException(status_code=404, detail="Resource not found")
    raise HTTPException(status_code=403, detail="Tenant is outside the authenticated tenant scope")


def resolve_tenant(principal: Principal, requested_tenant_id: Optional[str]) -> str:
    tenant_id = requested_tenant_id or principal.tenant_id
    require_tenant_access(principal, tenant_id)
    return tenant_id
