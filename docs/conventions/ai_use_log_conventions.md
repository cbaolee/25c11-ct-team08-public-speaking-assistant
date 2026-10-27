# AI Use Log Conventions

AI is allowed, but it must be declared, and the person who commits must be able to explain everything they add to the repo.

## 1. When to log

- **PR that uses AI:** add 1 line to your own log file and tick "AI usage declaration" in the PR template.
- **PR that does not use AI:** no log line is needed, just tick "No AI used" in the PR.

## 2. One-line log format

Append to the end of your own file, using the table below (create the table the first time you log):

```markdown
| Date       | PR / Issue | Tool   | What AI was used for                          |
| ---------- | ---------- | ------ | --------------------------------------------- |
| 2026-10-28 | #12 / 02   | Claude | Generated FastAPI scaffold and `/health` test |
```

## 3. Never put into a log or a prompt

- API keys, tokens, or the content of the `.env` file.
- Other people's personal data: verbatim interview content without consent, or voice recordings of members.
- Copyrighted PDFs or documents pasted verbatim into a public AI service.

## 4. What reviewers check

- Does the AI declaration in the PR match what was actually done?
- Does the log line in `docs/ai_use_log/` match the PR?
- Ask the author to explain 1-2 random functions or passages. If they cannot, the PR is not accepted.
