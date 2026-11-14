from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel

from src.app.config import settings

# TODO(auth): remove with the temporary stub below. UUID of the shared test account.
DEV_FALLBACK_USER_ID = "197a710c-4982-48d5-bcf5-b6cf03e61dce"


class CurrentUser(BaseModel):
    id: UUID


def get_current_user() -> CurrentUser:
    """Temporary stub. TODO(auth): the Auth team replaces this body with real token checks.

    Endpoints must get the user only through this dependency:
    `user: CurrentUser = Depends(get_current_user)`.
    Only works when APP_ENV=dev. Uses DEV_USER_ID from .env when set,
    otherwise the fixed test account DEV_FALLBACK_USER_ID.
    """
    if settings.app_env != "dev":
        raise HTTPException(status_code=401, detail="not_authenticated")
    try:
        user_id = UUID(settings.dev_user_id or DEV_FALLBACK_USER_ID)
    except ValueError as err:
        raise HTTPException(status_code=401, detail="not_authenticated") from err
    return CurrentUser(id=user_id)
