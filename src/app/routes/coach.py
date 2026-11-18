"""Authenticated, transient feedback for a saved session."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from src.app.coach_note import CoachNoteCache, generate_coach_note
from src.app.config import settings
from src.app.constants import CONSTANTS
from src.app.db.factory import Repos, get_repos
from src.app.db.models import StorageError
from src.app.deps import CurrentUser, get_current_user

router = APIRouter()
cache = CoachNoteCache(CONSTANTS['coach']['cache_ttl_s'])


@router.post('/api/sessions/{session_id}/coach-note')
async def coach_note(session_id: str, user: Annotated[CurrentUser, Depends(get_current_user)],
                     repos: Annotated[Repos, Depends(get_repos)]):
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        return JSONResponse(status_code=404, content={'error_code': 'session_not_found',
                                                      'message': 'Session not found.'})
    try:
        row = await run_in_threadpool(repos.sessions.get_session, user.id, session_uuid)
    except StorageError:
        return JSONResponse(status_code=503, content={'error_code': 'session_storage_unavailable',
                                                      'message': 'Session storage unavailable.'})
    if row is None:
        return JSONResponse(status_code=404, content={'error_code': 'session_not_found',
                                                      'message': 'Session not found.'})
    if row.status != 'ok':
        return JSONResponse(status_code=409, content={'error_code': 'insufficient_audio',
                                                      'message': 'Insufficient audio.'})
    note = cache.get(session_uuid)
    if note is None:
        note = await run_in_threadpool(generate_coach_note, row.result, settings)
        cache.put(session_uuid, note)
    return note
