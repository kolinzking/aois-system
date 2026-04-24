"""Role-based access control for AOIS API endpoints."""
from enum import Enum
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth.jwt_handler import decode_token
from jose import JWTError

_bearer = HTTPBearer()


class Role(str, Enum):
    viewer   = "viewer"    # read-only: list incidents, view analyses
    analyst  = "analyst"   # viewer + run investigations
    operator = "operator"  # analyst + approve remediations
    admin    = "admin"     # full access + manage users


_ROLE_HIERARCHY = {Role.viewer: 0, Role.analyst: 1, Role.operator: 2, Role.admin: 3}


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return {"user_id": payload["sub"], "role": payload["role"]}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_role(minimum_role: Role):
    """Dependency factory — enforces minimum role level."""
    def _check(user: dict = Depends(get_current_user)):
        user_level = _ROLE_HIERARCHY.get(Role(user["role"]), -1)
        required_level = _ROLE_HIERARCHY[minimum_role]
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{minimum_role}' or higher required. Your role: {user['role']}",
            )
        return user
    return _check
