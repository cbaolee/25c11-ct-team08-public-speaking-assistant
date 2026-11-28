| Date       | PR / Issue | Tool   | What AI was used for                                                                 |
| ---------- | ---------- | ------ | ------------------------------------------------------------------------------------ |
| 2026-10-30 | PB-05 | Gemini | Generated PoC Flow 1 scaffold (`parser.py`, `sanitizer.py`, `generator.py`) and tests |
| 2026-11-13 | #9 (WP-B2) | Antigravity | Implemented singleton SemanticRetriever and unit tests with offline mock             |
| 2026-11-13 | #9 (WP-B2) | Antigravity | Implemented deterministic citation verification and unit tests                      |
| 2026-11-13 | #9 (WP-B3) | Antigravity | Implemented TokenBucketLimiter in limiter.py and comprehensive unit tests            |
| 2026-11-13 | #9 (WP-B3) | Antigravity | Implemented parse_slots, regex assemble_template, and post-validator tests          |
| 2026-11-13 | #9 (WP-B3) | Antigravity | Implemented slot batching within token budget and 3-model fallback chain             |
| 2026-11-13 | #9 (WP-B3) | Antigravity | Implemented TemplateEngine orchestrator, RAG chunk retrieval, and unit tests        |
| 2026-11-20 | #57 | Antigravity | Implemented ephemeral chat session management, 0-token slot coverage, and unit tests |
| 2026-11-20 | #57 (Phase 2) | Antigravity | Implemented automated test suite for script generation chat scenarios 1-6 and Phase 2 workflow |
| 2026-11-25 | #120 (PR 1/3) | Antigravity | Implemented per-turn input limits, bounded context window, Groq compaction, continuous Q&A loop (Turn 1 can_generate=false / Turn 2+ can_generate=true), processing step telemetry, centralized `[script]` constants in `app_constants.toml`, ADR-014, architecture.md update, and expanded pytest suites |
| 2026-11-28 | #120 / #121 (Dev 2) | Antigravity | Implemented sentence-level citations (`SentenceCitation`), best-excerpt extraction, source provenance (`client_msg_id`, `source_kind`, `source_msg_id`, `source_file`), and unit/scenario/API tests |
