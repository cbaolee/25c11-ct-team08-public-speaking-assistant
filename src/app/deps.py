from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel

from src.app.config import settings


class CurrentUser(BaseModel):
    id: UUID


def get_current_user() -> CurrentUser:
    """Temporary stub. TODO(auth): the Auth team replaces this body with real token checks.

    Endpoints must get the user only through this dependency:
    `user: CurrentUser = Depends(get_current_user)`.
    """
    if settings.app_env != "dev" or not settings.dev_user_id:
        raise HTTPException(status_code=401, detail="not_authenticated")
    try:
        user_id = UUID(settings.dev_user_id)
    except ValueError as err:
        raise HTTPException(status_code=401, detail="not_authenticated") from err
    return CurrentUser(id=user_id)
