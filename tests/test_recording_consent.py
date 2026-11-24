"""Routes that take a recording need recording consent; routes that read past results do not.

Removes the `require_recording_consent` override from tests/conftest.py so the real check runs.
"""

import pytest
from conftest import TEST_USER_ID
from fastapi.testclient import TestClient

import src.app.main as main
from src.app.db.factory import get_repos
from src.app.db.models import ProfileUpsert, StorageError
from src.app.deps import require_recording_consent

RECORDING_ROUTES = [
    ("/api/evaluate", {"script": "Hello."}),
    ("/api/baseline", {}),
    ("/api/practice/retry", {"target_text": "hello", "kind": "word"}),
]


@pytest.fixture
def client():
    main.app.dependency_overrides.pop(require_recording_consent, None)  # real consent check
    return TestClient(main.app)


def _repos():
    return main.app.dependency_overrides[get_repos]()


def _make_profile(consent: bool) -> None:
    _repos().profiles.upsert_profile(TEST_USER_ID, ProfileUpsert(target_accent="American"))
    _repos().profiles.set_consent(TEST_USER_ID, consent)


def _post_audio(client, url, form):
    return client.post(url, data=form, files={"audio": ("a.wav", b"x")})


@pytest.mark.parametrize(("url", "form"), RECORDING_ROUTES)
def test_recording_routes_return_403_while_consent_is_off(client, url, form):
    _make_profile(consent=False)
    response = _post_audio(client, url, form)
    assert response.status_code == 403
    assert response.json()["error_code"] == "consent_required"


@pytest.mark.parametrize(("url", "form"), RECORDING_ROUTES)
def test_recording_routes_return_403_without_a_profile(client, url, form):
    assert _post_audio(client, url, form).status_code == 403


@pytest.mark.parametrize(("url", "form"), RECORDING_ROUTES)
def test_recording_routes_pass_the_check_with_consent(client, url, form):
    _make_profile(consent=True)
    assert _post_audio(client, url, form).status_code != 403


def test_profile_read_error_is_503(client, monkeypatch):
    def broken(_user_id):
        raise StorageError("down")

    monkeypatch.setattr(_repos().profiles, "get_profile", broken)
    response = _post_audio(client, "/api/baseline", {})
    assert response.status_code == 503


@pytest.mark.parametrize("url", ["/api/sessions", "/api/baseline"])
def test_past_results_stay_readable_while_consent_is_off(client, url):
    _make_profile(consent=False)
    assert client.get(url).status_code == 200
