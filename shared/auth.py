from typing import Any

import jwt
from fastapi import Header, HTTPException


def current_user(authorization: str = Header("")) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.replace("Bearer ", "")
    try:
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_iss": False,
                "verify_exp": False,
            },
        )
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")

    claims["roles"] = claims.get("realm_access", {}).get("roles", [])
    return claims


def require_admin(user: dict[str, Any]) -> None:
    roles = user.get("roles", [])
    scope = user.get("scope", "")
    if "marketplace-admin" not in roles and "admin:read" not in scope:
        raise HTTPException(status_code=403, detail="admin only")
