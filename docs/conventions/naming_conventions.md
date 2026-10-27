# Naming and Coding Conventions

Applies to the whole team. `ruff` (configured in `ruff.toml`) checks most of the code rules, including naming. Reviewers check the rest during PR review.

## 1. Branches

Pattern: `<type>/<issue number>-<short description>`

- Types: `feature`, `fix`, `docs`, `test`, `chore`, `spike`.
- Lowercase, words joined with hyphens, description up to about 40 characters, in English.
- Always create from the latest `develop`. Nobody pushes directly to `main` or `develop`.
- Delete the branch after merging.

## 2. Commits

```
<type>(<scope>): <subject>
```

| Type       | Use when                                     |
| ---------- | -------------------------------------------- |
| `feat`     | Adding a feature                             |
| `fix`      | Fixing a bug                                 |
| `docs`     | Documentation-only change                    |
| `test`     | Adding or changing tests                     |
| `chore`    | Config, tooling, dependencies, cleanup       |
| `refactor` | Restructuring code without changing behavior |

- Scope (optional): `app`, `text`, `audio`, `web`, `ci`, `docs`, `deps`.
- Subject up to about 72 characters.
- One commit does one thing. Keep commits small and frequent.
- Optionally add `Refs #number` in the body to link an issue.

## 3. Pull request titles

- Same format as commits: `<type>(<scope>): <subject>`. With squash merge, the PR title becomes the commit on `develop`.
- Open the PR as a **Draft** as soon as you have a partial result.
- Keep each PR under 300 changed lines and focused on one thing.
- Link the issue with `Closes #number` in the "Linked issue" section of the PR template.

## 4. Issues

- Backlog task title: `xx: <story name>` (for example `08: PoC Flow 1: PDF → Script`).
- Bug issue title: `bug: <short symptom>`.
- Every issue has an assignee, a type label, and a priority label.

## 5. Files and folders

| Kind                     | Convention                                      | Example                                         |
| ------------------------ | ----------------------------------------------- | ----------------------------------------------- |
| Python files and modules | `snake_case.py`                                 | `pdf_parser.py`, `stt_client.py`                |
| Test files               | `test_<module name>.py`                         | `test_scoring.py`                               |
| Folders                  | `snake_case`, lowercase                         | `text_processing`, `audio_processing`           |
| Numbered documents       | `NN_snake_case.md`                              | `01_project_brief.md`, `02_system_blueprint.md` |
| Regular documents        | `snake_case.md`                                 | `naming_conventions.md`                         |
| ADRs                     | `ADR-NNN.md`                                    | `ADR-001.md`                                    |
| Diagram files            | `snake_case.drawio` + `.png` with the same name | `flow1_script.drawio`                           |
| AI log files             | the member's GitHub username                    | `tuongvii2327.md`                               |

Never use spaces or accented characters in file names.

## 6. Tags

- Course documents: `v0.1-brief`, `v0.2-blueprint`, … `v0.5-mvp`.
- UI snapshots: `ui-snapshot-<sprint>` (for example `ui-snapshot-s5`).
- Only the team lead creates tags on `main`, after `develop` is merged into it.

## 7. Python code

| Item                     | Convention                       | Example                                      |
| ------------------------ | -------------------------------- | -------------------------------------------- |
| Variables, parameters    | `snake_case`, meaningful names   | `word_count`, `pause_list`                   |
| Functions, methods       | `snake_case`, start with a verb  | `parse_pdf()`, `calculate_wpm()`             |
| Classes, Pydantic models | `PascalCase`                     | `DocumentParser`, `ScriptResult`             |
| Constants                | `UPPER_SNAKE_CASE`               | `MAX_PDF_SIZE_MB`, `MIN_PAUSE_MS`            |
| Internal members         | leading `_`                      | `_clean_text()`                              |
| Boolean variables        | start with `is_`, `has_`, `can_` | `is_password_protected`                      |
| Variables with units     | put the unit at the end          | `pause_ms`, `file_size_mb`, `sample_rate_hz` |

- A clear name beats a short name. Do not use `x`, `tmp`, `data2`.
- Add type hints to the parameters and return values of public functions.
- Scoring functions are **pure functions**: the same input always gives the same output, with no API calls and no file reads.
- Never hardcode API keys. Read them from environment variables (see `.env.example`).
- No debug `print` in merged code. Use `logging`.
- Run `ruff check .` and `pytest` before pushing.

## 8. Data and API

- JSON keys and field names: `snake_case` (for example `start`, `end`, `word_count`, `insufficient_audio`).
- Endpoints: lowercase, plural nouns, joined with hyphens when needed (for example `GET /health`, `POST /scripts`, `POST /voice-evaluations`).
- Business error codes: short, stable `snake_case` (for example `insufficient_audio`).

## 9. Tests

- Test function name: `test_<function or feature>_<scenario>` (for example `test_calculate_wpm_empty_transcript`).
- Each test checks one thing. Use hand-calculated cases, and explain the numbers in a comment when they are not obvious.

## 10. Comments and docstrings

- Write in English, with simple words.
- Explain **why**, not what the code already says clearly.
- Short docstring for public functions: what it does, parameters, return value.

## 11. Documentation

- Write in English, short paragraphs, and use tables and lists for enumerations.
- Every figure must cite its source (interview file, measurement file). Never write an estimate as a result.
- Link to the related use case or module.
- Prefer Mermaid for diagrams so GitHub renders them directly. Use draw.io for the UI blueprint and export a PNG alongside.

## 12. Labels

- Labels use the form `<group>/<value>`, lowercase (for example `type/bug`, `area/audio`, `priority/must`).
