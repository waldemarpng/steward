"""Shared request dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from steward.service import Service

bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


async def token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
    """Bearer token from the Authorization header. 401 when it is missing."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(status_code=401, detail="invalid token", headers=_UNAUTHORIZED)
    return credentials.credentials


async def available(request: Request, raw: Annotated[str, Depends(token)]) -> dict[str, str]:
    """Decrypted secrets on a live grant, by name. 401 when the token cannot be used."""
    service: Service = request.app.state.service
    values = await service.issue_available(raw)
    if values is None:
        raise HTTPException(status_code=401, detail="invalid token", headers=_UNAUTHORIZED)
    return values
