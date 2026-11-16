from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.app.auth import AuthProvider, AuthUnavailableError, get_auth

_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: UUID
    email: str | None = None


def _not_authenticated() -> HTTPException:
    return HTTPException(
        status_code=401, detail="not_authenticated", headers={"WWW-Authenticate": "Bearer"}
    )


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """The raw access token from `Authorization: Bearer <token>`; 401 when it is missing."""
    if credentials is None or not credentials.credentials:
        raise _not_authenticated()
    return credentials.credentials


def get_current_user(
    token: Annotated[str, Depends(get_bearer_token)],
    auth: Annotated[AuthProvider, Depends(get_auth)],
) -> CurrentUser:
    """The logged-in user, from a verified access token.

    Endpoints must get the user only through this dependency:
    `user: CurrentUser = Depends(get_current_user)`. `user_id` never comes from the
    request body or query. 401 `not_authenticated` for a missing, invalid or expired
    token; 503 `auth_unavailable` when the account service cannot be reached.
    """
    try:
        token_user = auth.verify_token(token)
    except AuthUnavailableError as err:
        raise HTTPException(status_code=503, detail="auth_unavailable") from err
    if token_user is None:
        raise _not_authenticated()
    return CurrentUser(id=token_user.id, email=token_user.email)
