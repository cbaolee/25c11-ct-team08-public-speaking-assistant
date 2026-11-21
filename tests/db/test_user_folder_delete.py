"""list_user_files / delete_user_folder: every page, every batch, then the folder is empty."""

from uuid import uuid4

import pytest

from src.app.db.memory import MemoryAudioStore, MemoryState
from src.app.db.models import StorageError, build_avatar_path, build_object_path
from src.app.db.supabase_repo import STORAGE_LIST_PAGE, SupabaseAudioStore

USER = uuid4()
OTHER = uuid4()


class FakeBucket:
    """Storage bucket stub: list(folder, options) pages by offset/limit, remove() logs batches."""

    def __init__(self, names, *, fail_remove=False, keep_after_remove=False):
        self.objects = set(names)
        self.removed_batches = []
        self.list_calls = []
        self.fail_remove = fail_remove
        self.keep_after_remove = keep_after_remove

    def list(self, folder, options):
        self.list_calls.append((folder, options["offset"]))
        prefix = folder + "/"
        children = sorted({n[len(prefix):].split("/")[0] for n in self.objects
                           if n.startswith(prefix)})
        entries = [
            {"name": c, "id": None if any(n.startswith(prefix + c + "/") for n in self.objects)
             else "id-" + c}
            for c in children
        ]
        start = options["offset"]
        return entries[start : start + options["limit"]]

    def remove(self, paths):
        if self.fail_remove:
            raise RuntimeError("storage down")
        assert len(paths) <= STORAGE_LIST_PAGE
        self.removed_batches.append(list(paths))
        if not self.keep_after_remove:
            self.objects -= set(paths)
        return []


class FakeClient:
    def __init__(self, bucket):
        self.storage = self
        self.bucket = bucket

    def from_(self, name):
        return self.bucket


def _names(n, user=USER):
    return [build_object_path(user, uuid4(), ".webm") for _ in range(n)]


def test_supabase_lists_every_page_and_deletes_in_batches():
    mine = _names(2 * STORAGE_LIST_PAGE + 50)
    others = _names(3, OTHER)
    bucket = FakeBucket(mine + others)
    store = SupabaseAudioStore(FakeClient(bucket))
    assert store.list_user_files(USER, "audio") == sorted(mine)
    store.delete_user_folder(USER, "audio")
    assert [len(b) for b in bucket.removed_batches] == [100, 100, 50]
    assert bucket.objects == set(others)  # another user's folder is untouched


def test_supabase_lists_sub_folders_too():
    nested = f"{USER}/old/{uuid4()}.webm"
    bucket = FakeBucket([nested, build_avatar_path(USER)])
    store = SupabaseAudioStore(FakeClient(bucket))
    assert store.list_user_files(USER, "avatars") == sorted([nested, build_avatar_path(USER)])


def test_supabase_delete_fails_when_folder_is_not_empty_after_delete():
    bucket = FakeBucket(_names(3), keep_after_remove=True)
    with pytest.raises(StorageError):
        SupabaseAudioStore(FakeClient(bucket)).delete_user_folder(USER, "audio")


def test_supabase_storage_error_becomes_storage_error():
    bucket = FakeBucket(_names(1), fail_remove=True)
    with pytest.raises(StorageError):
        SupabaseAudioStore(FakeClient(bucket)).delete_user_folder(USER, "audio")


def test_supabase_empty_folder_is_a_no_op():
    bucket = FakeBucket([])
    SupabaseAudioStore(FakeClient(bucket)).delete_user_folder(USER, "audio")
    assert bucket.removed_batches == []


def test_memory_delete_user_folder_keeps_other_buckets_and_users():
    state = MemoryState()
    store = MemoryAudioStore(state)
    mine, theirs = _names(1)[0], _names(1, OTHER)[0]
    store.upload_file(USER, "audio", mine, b"x", "audio/webm")
    store.upload_file(USER, "series", build_object_path(USER, uuid4(), ".series.json"), b"{}",
                      "application/json")
    store.upload_file(OTHER, "audio", theirs, b"y", "audio/webm")
    store.delete_user_folder(USER, "audio")
    assert store.list_user_files(USER, "audio") == []
    assert len(store.list_user_files(USER, "series")) == 1
    assert store.list_user_files(OTHER, "audio") == [theirs]
    store.delete_user_folder(USER, "audio")  # idempotent
