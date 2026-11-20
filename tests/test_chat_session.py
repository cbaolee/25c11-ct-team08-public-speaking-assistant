"""Unit tests for Phase 1: ChatSessionState, ChatSessionStore, and minimal-token gathering."""

from __future__ import annotations

import re
import sys
import threading
import time
import types
import zlib
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.text_processing.chat_session import (
    GROUP_COUNTER,
    GROUP_EVIDENCE,
    GROUP_MAIN,
    READY_MESSAGE,
    ChatSessionState,
    ChatSessionStore,
    analyze_slot_coverage,
    build_followup_reply,
    check_ready_to_generate,
    classify_argument_slot,
    group_uncovered_slots,
    ingest_upload_file,
)
from src.text_processing.contracts import (
    DocumentChunk,
    TemplateDocument,
    TopicMetadata,
)
class TestChatSessionStore:
    def test_store_put_and_get_success(self) -> None:
        store = ChatSessionStore(capacity=10, ttl_seconds=60.0)
        state = ChatSessionState(
            session_id="s1",
            user_id="user_123",
            category="Sports",
            duration_min=5,
        )
        store.put(state)
        retrieved = store.get("s1", user_id="user_123")
        assert retrieved is not None
        assert retrieved.session_id == "s1"
        assert retrieved.user_id == "user_123"

    def test_store_user_id_isolation(self) -> None:
        store = ChatSessionStore(capacity=10, ttl_seconds=60.0)
        state = ChatSessionState(
            session_id="s_private",
            user_id="user_alice",
            category="Wildlife",
            duration_min=10,
        )
        store.put(state)

        # Bob attempts to access Alice's session
        bob_access = store.get("s_private", user_id="user_bob")
        assert bob_access is None

        # Alice accesses her own session
        alice_access = store.get("s_private", user_id="user_alice")
        assert alice_access is not None

    def test_store_sliding_ttl_expiration(self) -> None:
        store = ChatSessionStore(capacity=10, ttl_seconds=0.05)
        state = ChatSessionState(
            session_id="s_expire",
            user_id="user_alice",
            category="IT",
            duration_min=5,
        )
        store.put(state)
        time.sleep(0.08)

        # Should be expired and return None
        assert store.get("s_expire", user_id="user_alice") is None
        assert len(store) == 0

    def test_store_capacity_eviction_lru(self) -> None:
        store = ChatSessionStore(capacity=3, ttl_seconds=60.0)
        for i in range(1, 4):
            store.put(
                ChatSessionState(
                    session_id=f"s{i}",
                    user_id="u1",
