# Public Speaking Coach

AI assistant for English learners: generate MC scripts from your documents and get feedback on your spoken practice.

Computational Thinking course project, HCMUS, class 25C11, Team 08.

## Table of Contents

- [About](#about)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Team](#team)
- [License](#license)

## About

Public Speaking Coach is a web app that helps English learners prepare and practice presentations. Learners get a ready-to-read script from their own material, then record themselves and receive measurable feedback on pace, pauses, and accuracy against the script.

## Features

| Feature               | Description                                                                                                                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Script Generating** | Pick a topic and upload a PDF or type text. The system extracts the content, checks it for safety, and generates an English MC script.                                                                        |
| **Voice Evaluate**    | Record or upload audio. The system transcribes the speech, measures speaking pace (WPM) and pauses, and compares the transcript with the script to produce a score.                                           |
| **Baseline**          | A short voice sample is analysed once and kept as the user's current baseline. Every evaluation is scored against the baseline stored on the server.                                                          |
| **Session History**   | Each evaluated session is saved with its audio and chart data. The newest 10 sessions stay complete; the next 30 keep only scores, script and mistakes; older ones are deleted. |
| **Saved Scripts**     | Up to 10 named scripts per user, editable, shared by Practice and Script Studio. Practising a script does not save it.                                                                                        |
| **Follow-along**      | While recording, the current sentence is highlighted at a chosen speed. Tapping a sentence moves the highlight there; with Auto speed on, the taps also set the speed. Range and Auto speed are in Settings. |
| **Profile**           | Display name, accent, recording consent, profile picture and reading-speed preferences, stored per account.                                                                                       |
| **Account**           | Email + password with email verification. Changing the password or deleting the account asks for the current password; deleting removes recordings, baseline, scripts and history. Settings > Audio picks the microphone (kept in this browser). |

## Tech Stack

- **Language:** Python 3.12
- **Backend:** FastAPI, Uvicorn
- **AI services:** Groq API (LLM for scripts), Deepgram (speech-to-text) with Gladia as fallback
- **Document processing:** PyMuPDF4LLM
- **Audio processing:** FFmpeg, Silero VAD
- **Scoring:** jiwer
- **Database & storage:** Supabase (PostgreSQL, Storage), `supabase` Python client
- **Frontend:** HTML, CSS, JavaScript ES modules (no build step)
- **Tooling:** uv, Ruff, pytest, GitHub Actions

## Getting Started

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- [FFmpeg](https://ffmpeg.org/) available on your `PATH` (also used to encode stored audio as Opus)
- API keys for [Groq](https://console.groq.com/), [Deepgram](https://deepgram.com/) and [Gladia](https://www.gladia.io/) (the server does not start without them)
- Access to the team's [Supabase](https://supabase.com/) projects `psc-main` and `psc-shard01` … `psc-shard09` (optional for local runs, see [Database setup](#database-setup))

### Installation

```bash
git clone https://github.com/cbaolee/25c11-ct-team08-public-speaking-assistant.git
cd 25c11-ct-team08-public-speaking-assistant
uv sync
```

### Configuration

Copy `.env.example` to `.env` and fill in your own values. Never commit `.env` and never paste keys into chat or AI tools.

```bash
cp .env.example .env
```

API keys (required). Each variable takes one or more keys separated by commas, for example `GROQ_API_KEYS=key1,key2`:

| Variable            | Description                                                                              |
| ------------------- | ---------------------------------------------------------------------------------------- |
| `DEEPGRAM_API_KEYS` | Speech-to-text, tried first.                                                             |
| `GLADIA_API_KEYS`   | Speech-to-text fallback, used after every Deepgram key has failed.                       |
| `GROQ_API_KEYS`     | Script generation. Every key is tried for one model before moving to the fallback model. |

When a key runs out of quota (HTTP 429 or 402) the server switches to the next key and tries the locked one again after `exhausted_cooldown_s` (`app_constants.toml`, default 600 s). A refused key (401 or 403) is skipped until restart. Logs name keys by position (`groq key #2`), never by value. The old single-key names (`DEEPGRAM_API_KEY`, `GLADIA_API_KEY`, `GROQ_API_KEY`) are no longer read: rename them in your `.env`.

Database and storage variables:

| Variable               | Required            | Description                                                                                                                                                                                                     |
| ---------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `APP_ENV`              | Yes                 | `dev` locally. Any other value disables the temporary dev user.                                                                                                                                                 |
| `SUPABASE_URL`         | No                  | Project URL `https://<ref>.supabase.co` from _Project Settings → API_, **without** `/rest/v1/` (the server refuses to start with it). Empty in `dev` = in-memory storage and accounts, data is lost on restart. |
| `SUPABASE_SERVICE_KEY` | With `SUPABASE_URL` | Server-side key (`service_role` / `secret`). Full database access: keep it private.                                                                                                                             |
| `DEV_USER_ID`          | Integration tests   | UUID of a first test user, only read by integration tests. The app itself uses real log in (`/api/auth/*`).                                                                                                     |
| `DEV2_USER_ID`         | Integration tests   | UUID of a second test user, only read by integration tests.                                                                                                                                                     |

Optional settings: `BASELINE_REQUIRED` (`true`), `RETENTION_FULL_SESSIONS` (`10`), `MAX_COMPACT_SESSIONS` (`30`), `SIGNED_URL_TTL_S` (`600`), and the bucket names `AUDIO_BUCKET`, `SERIES_BUCKET`, `BASELINES_BUCKET`, `AVATARS_BUCKET`.

Tunable limits (saved-script cap, avatar size, list page size, UI timings and follow-along speeds) are in `app_constants.toml`, one comment per key. Restart the server after a change.

### Database setup

Only needed when `SUPABASE_URL` is set.

1. **Enable `pg_cron`** on every project (_Database → Extensions_): each one runs a cleanup job. Full order for a new core or shard project: [architecture.md 4.7](architecture.md).
   **Run the migrations** in order on the core project `psc-main` (_SQL Editor_ → paste → _Run_). Back up first and update the file's `Applied:` line after running it.

   | File | Run | Creates |
   | --- | --- | --- |
   | `0001_init.sql` | once | Tables, indexes, row level security, grants |
   | `0002_storage.sql` | once | Private buckets `audio`, `series`, `baselines` and their policies |
   | `0003_profile_avatar_preferences.sql` | any time | `profiles.avatar_path`, `profiles.preferences`, bucket `avatars`, function `merge_profile_preferences` |
   | `0004_replace_baseline_fn.sql` | any time | Function `replace_current_baseline` (baseline swap in one transaction) |
   | `0005_purge_insufficient_sessions.sql` | required, any time | pg_cron job that deletes `insufficient_audio` sessions older than 7 days (must match `app_constants.toml` `[retention] insufficient_days`). Enable the `pg_cron` extension first (Dashboard -> Database -> Extensions). Until it has run, insufficient sessions are not deleted even though the UI says "deleted after 7 days". |
   | `0006_scripts_title_body_only.sql` | once | `scripts` keeps only title and body; unique title and body per user |
   | `0007_drop_profile_topics.sql` | once | Drops `profiles.topics` |
   | `0008_replace_baseline_delete_old.sql` | any time | `replace_current_baseline` keeps one baseline row per user |
   | `0009_purge_unconfirmed_accounts.sql` | required, any time | pg_cron job (every 15 min) that deletes accounts whose email is still unconfirmed 60 minutes after the last code (must match `app_constants.toml` `[auth] unconfirmed_ttl_min`); accounts with files in Storage are skipped. Enable `pg_cron` first. Until it has run, unconfirmed accounts stay even though the "Check your email" step says they are deleted (ADR-011). |
   | `0010_accounts.sql` | any time | Table `accounts` (which shard holds each user's sessions); existing users get `core` |

   On every **shard project** (ADR-012) run `db/migrations/shard/0001_sessions.sql` (once), then `shard/0002_purge_insufficient_sessions.sql` (enable pg_cron first), then list the shards in `SUPABASE_SHARDS`.

   Deploy a backend version only after the migrations it needs have run.
2. **Create test users** on `psc-main` only: _Authentication → Users → Add user_. Put the first UUID in `DEV_USER_ID` and the second in `DEV2_USER_ID`.
3. **Create a `profiles` row for each test user.** Baselines, scripts and sessions reference `profiles(id)`, so saving fails for a user without a profile.
4. Record a baseline once for your test user: with `BASELINE_REQUIRED=true`, `/api/evaluate` returns `409 baseline_required` until a baseline exists.

> Never edit a merged migration, except its `Applied:` line. Add a new file (`0011_...sql`, or the next number in `shard/`) with the `Run` / `Applied` / `Effect` header. Run it on every project it is for (core or each shard).

### Testing

```bash
uv run pytest                                   # unit tests, no network or keys needed
uv run pytest -m integration                    # real Supabase tests on psc-main and the shards
node --test tests/web/evaluate_client.test.js   # UI helper tests
```

Integration tests are skipped by default. They need `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DEV_USER_ID` and `DEV2_USER_ID`, both users with a `profiles` row, and all migrations applied.

### Code style

```bash
uv run ruff check .
```

## Usage

Run every command from the repository root (the app reads `.env` from there).

```bash
uv run uvicorn src.app.main:app --reload --port 8000
```

Then open <http://localhost:8000> in the browser on the same machine. Browsers only allow the
microphone on `localhost` or HTTPS.

1. **Sign up** with an email and a password (at least 8 characters), choose your accent.
2. **Record your baseline**: the Baseline Gate asks for 30 seconds of normal reading once.
3. **Script Studio**: pick a template topic or describe your event (or attach a PDF up to 10 pages), then save the script.
4. **Practice**: choose a saved script, your own text or a sample, then record (pause and resume allowed) or upload your voice.
5. **Report**: scores for accuracy, fluency, pronunciation and meaning, with every marked word. An evaluation longer than 5 seconds continues in the background and the report is offered when ready.
   Home and History keep your sessions; the 10 newest keep their audio and charts.

A demo needs Internet access (Supabase, speech-to-text, Groq) and the Supabase project must not be paused.

## Project Structure

```
.
├── .github/
│   ├── workflows/ci.yml           # CI: ruff + pytest + JS tests
│   ├── pull_request_template.md
│   └── issue_template.md
├── db/
│   └── migrations/                # SQL migrations for Supabase (schema, RLS, buckets, functions)
├── docs/
│   ├── adr/                       # Architecture decision records
│   ├── ai_use_log/                # AI usage logs, one file per member
│   ├── conventions/               # Team conventions
│   ├── challenge_analysis.md
│   ├── use_case.drawio
│   ├── input_flow.drawio
│   ├── script_generating.drawio
│   └── voice_evaluate_pipeline.drawio
├── src/
│   ├── app/
│   │   ├── db/                    # Repository layer: models, interfaces, Supabase and in-memory versions
│   │   ├── routes/                # Auth, profile and baseline endpoints
│   │   ├── auth.py                # Accounts: Supabase Auth, or in memory without Supabase
│   │   ├── config.py              # Settings from .env and app_constants.toml, start-up checks
│   │   ├── deps.py                # Current user from the Bearer access token
│   │   └── main.py                # FastAPI app: evaluate, scripts, session history, config
│   ├── audio_processing/          # Evaluate and Baseline Pipeline
│   ├── text_processing/           # Script Pipeline
│   └── web/                       # index.html, CSS, ES modules
├── tests/
│   ├── db/                        # Repository and session helper tests
│   └── web/                       # Node tests for evaluate_client.js
├── .env.example
├── .gitattributes
├── .gitignore
├── app_constants.toml             # Tunable limits and UI settings
├── architecture.md
├── pyproject.toml
├── uv.lock
├── ruff.toml
└── README.md
```

## Documentation

- [Architecture](architecture.md)
- Decision records: [ADR-001 Data model](docs/adr/ADR-001.md), [ADR-002 Evaluate response save status](docs/adr/ADR-002.md), [ADR-006 Moderation layer 2](docs/adr/ADR-006.md)
- [Technical challenge analysis](docs/challenge_analysis.md)
- [Naming and coding conventions](docs/conventions/naming_conventions.md)
- [AI use log conventions](docs/conventions/ai_use_log_conventions.md)
- Diagrams (open with [draw.io](https://app.diagrams.net/)): [use case](docs/use_case.drawio), [UI flow](docs/input_flow.drawio), [Script Generating](docs/script_generating.drawio), [Voice Evaluate](docs/voice_evaluate_pipeline.drawio)

## Contributing

Every change follows one path:

**Issue → own branch → Pull Request into `develop` → review + CI → merge**

1. Never push directly to `main` or `develop`.
2. Name branches, commits, and PRs following the [naming conventions](docs/conventions/naming_conventions.md).
3. Every PR needs a green CI and at least 1 approval.
4. Declare any AI you used in the PR and log it in `docs/ai_use_log/` following the [conventions](docs/conventions/ai_use_log_conventions.md).

## Team

<!-- TODO -->

## License

<!-- TODO -->
