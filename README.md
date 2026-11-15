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

| Feature | Description |
|---|---|
| **Script Generating** | Pick a topic and upload a PDF or type text. The system extracts the content, checks it for safety, and generates an English MC script. |
| **Voice Evaluate** | Record or upload audio. The system transcribes the speech, measures speaking pace (WPM) and pauses, and compares the transcript with the script to produce a score. |
| **Baseline** | A short voice sample is analysed once and kept as the user's current baseline. Every evaluation is scored against the baseline stored on the server. |
| **Session History** | Each evaluated session is saved with its audio and chart data. The newest 10 sessions stay complete; older ones keep only scores, script and mistakes. Backend API only, see [Architecture](architecture.md). |

## Tech Stack

- **Language:** Python 3.12
- **Backend:** FastAPI, Uvicorn
- **AI services:** Groq API (LLM and Whisper speech-to-text)
- **Document processing:** PyMuPDF4LLM
- **Audio processing:** FFmpeg, Silero VAD
- **Scoring:** jiwer
- **Database & storage:** Supabase (PostgreSQL, Storage), `supabase` Python client
- **Frontend:** HTML, Tailwind CSS
- **Tooling:** uv, Ruff, pytest, GitHub Actions

## Getting Started

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- [FFmpeg](https://ffmpeg.org/) available on your `PATH` (also used to encode stored audio as Opus)
- A [Groq](https://console.groq.com/) API key
- Access to the team's [Supabase](https://supabase.com/) project `psc-dev` (optional for local runs, see [Database setup](#database-setup))

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

Database and storage variables:

| Variable | Required | Description |
| --- | --- | --- |
| `APP_ENV` | Yes | `dev` locally. Any other value disables the temporary dev user. |
| `SUPABASE_URL` | No | Project URL from *Project Settings → API*. Empty in `dev` = in-memory storage, data is lost on restart. |
| `SUPABASE_SERVICE_KEY` | With `SUPABASE_URL` | Server-side key (`service_role` / `secret`). Full database access: keep it private. |
| `DEV_USER_ID` | No | UUID of your test user on `psc-dev`. Empty = the shared test account. Temporary until real auth is merged. |
| `DEV2_USER_ID` | Integration tests | UUID of a second test user, only read by integration tests. |

Optional settings with defaults in `src/app/config.py`: `BASELINE_REQUIRED` (`true`), `RETENTION_FULL_SESSIONS` (`10`), `SIGNED_URL_TTL_S` (`600`), and the bucket names `AUDIO_BUCKET`, `SERIES_BUCKET`, `BASELINES_BUCKET`.

### Database setup

Only needed when `SUPABASE_URL` is set.

1. **Run the migrations** in order on the Supabase project (*SQL Editor* → paste → *Run*):
   - `db/migrations/0001_init.sql`: tables, indexes, row level security, grants
   - `db/migrations/0002_storage.sql`: private buckets `audio`, `series`, `baselines` and their policies
2. **Create test users** on `psc-dev` only: *Authentication → Users → Add user*. Put the first UUID in `DEV_USER_ID` and the second in `DEV2_USER_ID`.
3. **Create a `profiles` row for each test user.** Baselines, scripts and sessions reference `profiles(id)`, so saving fails for a user without a profile.
4. Record a baseline once for your test user: with `BASELINE_REQUIRED=true`, `/api/evaluate` returns `409 baseline_required` until a baseline exists.

> Never edit a merged migration. Add a new file (`0003_...sql`) instead. Run migrations on `psc-dev` first.

### Testing

```bash
uv run pytest                    # unit tests, no network or keys needed
uv run pytest -m integration     # real Supabase tests on psc-dev
```

Integration tests are skipped by default. They need `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DEV_USER_ID` and `DEV2_USER_ID`, and both users must have a `profiles` row.

### Code style

```bash
uv run ruff check .
```

## Usage

<!-- TODO -->

## Project Structure

```
.
├── .github/
│   ├── workflows/ci.yml           # CI: ruff + pytest
│   ├── pull_request_template.md
│   └── issue_template.md
├── db/
│   └── migrations/                # SQL migrations for Supabase (schema, RLS, buckets)
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
│   └── app/
│       ├── db/                    # Repository layer: models, interfaces, Supabase and in-memory versions
│       ├── routes/                # Baseline endpoints
│       ├── config.py              # Settings read from .env
│       ├── deps.py                # Current user dependency (temporary dev stub)
│       └── main.py                # FastAPI app, evaluate and session history endpoints
├── tests/
│   └── db/                        # Repository and session helper tests
├── .env.example
├── .gitattributes
├── .gitignore
├── architecture.md
├── pyproject.toml
├── uv.lock
├── ruff.toml
└── README.md
```

## Documentation

- [Architecture](architecture.md)
- Decision records: [ADR-001 Data model](docs/adr/ADR-001.md), [ADR-002 Evaluate response save status](docs/adr/ADR-002.md)
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
