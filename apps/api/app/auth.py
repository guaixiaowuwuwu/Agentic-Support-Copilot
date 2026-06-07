from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Set

from fastapi import Header, HTTPException


READ_ROLES = {"support_agent", "approver", "knowledge_admin", "admin"}
RUN_ROLES = {"support_agent", "approver", "admin"}
APPROVAL_DECISION_ROLES = {"approver", "admin"}
KNOWLEDGE_WRITE_ROLES = {"knowledge_admin", "admin"}


@dataclass(frozen=True)
class Principal:
    email: str
    tenant_id: str
    tenant_ids: Set[str]
    roles: Set[str]

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
        }


def _split_header(value: Optional[str], *, lower: bool = False) -> Set[str]:
    if not value:
        return set()
    items = {item.strip() for item in value.split(",") if item.strip()}
    if lower:
        return {item.lower() for item in items}
    return items


def get_current_principal(
    user_email: Optional[str] = Header(default=None, alias="X-User-Email"),
    tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
    user_roles: Optional[str] = Header(default=None, alias="X-User-Roles"),
    tenant_ids: Optional[str] = Header(default=None, alias="X-Tenant-Ids"),
) -> Principal:
    if not user_email or not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication headers are required")

    roles = _split_header(user_roles, lower=True)
    if not roles:
        raise HTTPException(status_code=403, detail="At least one user role is required")

    scoped_tenant_ids = _split_header(tenant_ids) or {tenant_id}
    if tenant_id not in scoped_tenant_ids:
        raise HTTPException(status_code=403, detail="Active tenant is outside the authenticated tenant scope")

    return Principal(
        email=user_email.strip(),
        tenant_id=tenant_id.strip(),
        tenant_ids=scoped_tenant_ids,
        roles=roles,
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
