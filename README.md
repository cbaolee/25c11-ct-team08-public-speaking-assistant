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

## Tech Stack

- **Language:** Python 3.12
- **Backend:** FastAPI, Uvicorn
- **AI services:** Groq API (LLM and Whisper speech-to-text)
- **Document processing:** PyMuPDF4LLM
- **Audio processing:** FFmpeg, Silero VAD
- **Scoring:** jiwer
- **Frontend:** HTML, Tailwind CSS
- **Tooling:** Ruff, pytest, GitHub Actions

## Getting Started

### Prerequisites

- Python 3.12
- [FFmpeg](https://ffmpeg.org/) available on your `PATH`
- A [Groq](https://console.groq.com/) API key

### Installation

```bash
git clone https://github.com/cbaolee/25c11-ct-team08-public-speaking-assistant.git
cd 25c11-ct-team08-public-speaking-assistant

python -m venv .venv
.venv/Scripts/activate        # Windows (Git Bash); on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your own values. Never commit `.env`.

```bash
cp .env.example .env
```

### Code style

```bash
ruff check .
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
├── docs/
│   ├── ai_use_log/                # AI usage logs, one file per member
│   ├── conventions/               # Team conventions
│   ├── challenge_analysis.md
│   ├── use_case.drawio
│   ├── input_flow.drawio
│   ├── script_generating.drawio
│   └── voice_evaluate_pipeline.drawio
├── .env.example
├── .gitattributes
├── .gitignore
├── architecture.md
├── requirements.txt
├── ruff.toml
└── README.md
```

## Documentation

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
