"""WP-B0 (Member 1): Template Store and Template Linter.

Responsibilities (Brief §5.3, §5.4):
- Load markdown templates from `data/templates/<category_slug>/<topic_slug>.md`
- Validate frontmatter (`topic`, `category`, `duration_min` in {5, 10, 15, 20})
- Index templates by `template_id` ("<category_slug>/<topic_slug>") and topic name
- Provide `list_topics()` for `GET /api/topics`
- Provide `lint_template_file()` for pytest validation of the 600-template repository
"""

import re
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .contracts import CATEGORY_SLUG_MAP, VALID_DURATIONS, TemplateDocument, TopicMetadata

DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "data" / "templates"
FRONTMATTER_RE = re.compile(
    r"^---\r?\n"
    r'topic:\s*"([^"]+)"\r?\n'
    r'category:\s*"([^"]+)"\r?\n'
    r"duration_min:\s*(\d+)\r?\n"
    r"---\r?\n(.*)$",
    re.DOTALL,
)
SLOT_RE = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
# Each alternative of the quoted string starts with a different character: no backtracking blow-up.
_QUOTED = r'"((?:[^"\\]|\\["\\])*)"[ \t]*'
_HEADER_RES = (
    ("topic", re.compile(rf"topic:[ \t]*{_QUOTED}")),
    ("category", re.compile(rf"category:[ \t]*{_QUOTED}")),
    ("duration_min", re.compile(r"duration_min:[ \t]*([0-9]{1,9})[ \t]*")),
)
# Linter-only: a slot glued to an extra `{` or `}` (`{{{ x }}`) is not valid, unlike SLOT_RE.
_STRICT_SLOT_RE = re.compile(r"(?<!\{)\{\{\s*[a-z0-9_]+\s*\}\}(?!\})")
_UNESCAPE_RE =re.compile(r'\\(["\\])')
_HEADING_RE = re.compile(r"#{1,6}(?:[ \t]|$)")

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class LintIssue:
    """One lint finding. `message` has no template prose (at most a `[a-z0-9_]` slot name)."""

    rule: str
    severity: Severity
    message: str
    path: str
    line: int | None = None


class TemplateFormatError(ValueError):
    """Raised by `parse_front_matter` when the front matter violates Brief §5.3."""

    def __init__(self, rule: str, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.rule, self.message, self.line = rule, message, line


@dataclass(frozen=True)
class ParsedTemplate:
    """Front matter values plus the raw body; `body_start_line` is 1-based."""

    topic: str
    category: str
    duration_min: int
    body: str
    body_start_line: int


def slugify_topic(topic: str) -> str:
    """Convert a topic title into a clean snake_case slug (Brief §5.3)."""
    cleaned = re.sub(r"[^a-z0-9\s_]", "", topic.lower())
    return re.sub(r"[\s_]+", "_", cleaned).strip("_")


def _normalize(raw: str) -> str:
    return raw.removeprefix("﻿").replace("\r\n", "\n")


def read_template_text(path: Path) -> str:
    """Read a template as UTF-8, dropping a BOM and converting CRLF to LF."""
    return _normalize(path.read_bytes().decode("utf-8-sig"))


def parse_front_matter(raw: str) -> ParsedTemplate:
    """Parse the strict 3-key front matter (topic, category, duration_min, in that order)."""
    lines = _normalize(raw).split("\n")
    if lines[0].rstrip() != "---":
        raise TemplateFormatError("frontmatter_format", "Line 1 must be '---'.", 1)
    values: list[str] = []
    for offset, (key, pattern) in enumerate(_HEADER_RES, start=1):
        match = pattern.fullmatch(lines[offset]) if offset < len(lines) else None
        if match is None:
            msg = f"Line {offset + 1}: expected '{key}' (order: topic, category, duration_min)."
            raise TemplateFormatError("frontmatter_format", msg, offset + 1)
        values.append(match.group(1))
    if len(lines) < 5 or lines[4].rstrip() != "---":
        raise TemplateFormatError("frontmatter_format", "Line 5 must close with '---'.", 5)
    topic, category, duration = values
    return ParsedTemplate(
        topic=_UNESCAPE_RE.sub(r"\1", topic),
        category=_UNESCAPE_RE.sub(r"\1", category),
        duration_min=int(duration),
        body="\n".join(lines[5:]),
        body_start_line=6,
    )


def find_slots(body: str) -> list[tuple[str, int]]:
    """Return `(slot_name, 1-based line within body)` for every valid `{{ name }}` slot."""
    newlines = [i for i, ch in enumerate(body) if ch == "\n"]
    return [(m.group(1), bisect_left(newlines, m.start()) + 1) for m in SLOT_RE.finditer(body)]


def lint_template_text(raw: str, *, category_slug: str, path: str = "") -> list[LintIssue]:
    """Lint one template's text against Brief §5.3 (front matter, slots, headings)."""

    def issue(rule: str, msg: str, line: int | None = None) -> LintIssue:
        return LintIssue(rule, "error", msg, path, line)

    try:
        tpl = parse_front_matter(raw)
    except TemplateFormatError as exc:
        return [issue(exc.rule, exc.message, exc.line)]

    out: list[LintIssue] = []
    expected_category = CATEGORY_SLUG_MAP.get(category_slug)
    if expected_category is None:
        out.append(issue("unknown_category_dir", "Directory is not a known category slug."))
    elif tpl.category != expected_category:
        out.append(issue("category_mismatch", "`category` differs from its directory.", 3))
    if tpl.duration_min not in VALID_DURATIONS:
        out.append(issue("duration_invalid", "duration_min must be 5, 10, 15 or 20.", 4))
    if not tpl.topic.strip():
        out.append(issue("topic_empty", "`topic` is empty.", 2))
    if not tpl.body.strip():
        out.append(issue("body_empty", "Template body is empty."))

    offset = tpl.body_start_line - 1
    leftover = _STRICT_SLOT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), tpl.body)
    for n, line in enumerate(leftover.split("\n"), start=1):
        if "{{" in line or "}}" in line:
            out.append(issue("slot_syntax", "Slot must be '{{ name }}' ([a-z0-9_]).", n + offset))
    for n, line in enumerate(tpl.body.split("\n"), start=1):
        if _HEADING_RE.match(line):
            out.append(issue("markdown_heading", "Markdown headings are not allowed.", n + offset))
    reported: set[str] = set()
    seen: set[str] = set()
    for name, n in find_slots(tpl.body):
        if name.startswith("argument_") and name in seen and name not in reported:
            reported.add(name)
            out.append(issue("argument_slot_repeated", f"Slot '{name}' repeats.", n + offset))
        seen.add(name)
    return out


def lint_template_file(file_path: Path, templates_dir: Path | None = None) -> list[LintIssue]:
    """Lint a single template file; `path` in issues is relative to `templates_dir` if given."""
    rel = file_path.as_posix()
    if templates_dir is not None and file_path.is_relative_to(templates_dir):
        rel = file_path.relative_to(templates_dir).as_posix()
    if not file_path.is_file():
        return [LintIssue("file_not_found", "error", "File does not exist.", rel)]
    try:
        raw = read_template_text(file_path)
    except UnicodeDecodeError:
        return [LintIssue("encoding", "error", "File is not valid UTF-8.", rel)]
    return lint_template_text(raw, category_slug=file_path.parent.name, path=rel)


class TemplateStore:
    """In-memory index of markdown script templates loaded at startup (Brief §5.4)."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        self.templates_dir = templates_dir or DEFAULT_TEMPLATES_DIR
        self._by_id: dict[str, TemplateDocument] = {}
        self._by_topic_lower: dict[str, TemplateDocument] = {}

    def load(self) -> int:
        """Scan `self.templates_dir` and index all valid `.md` templates.

        Returns the number of loaded templates.
        TODO (Member 1 - WP-B0): Refine slug resolution and strict validation if needed.
        """
        self._by_id.clear()
        self._by_topic_lower.clear()
        if not self.templates_dir.exists():
            return 0

        for category_dir in sorted(self.templates_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            category_slug = category_dir.name
            for md_file in sorted(category_dir.glob("*.md")):
                raw = md_file.read_text(encoding="utf-8")
                match = FRONTMATTER_RE.match(raw)
                if not match:
                    continue
                topic, category, duration_str, body = match.groups()
                duration_min = int(duration_str)
                if duration_min not in VALID_DURATIONS:
                    continue
                topic_slug = md_file.stem
                template_id = f"{category_slug}/{topic_slug}"
                meta = TopicMetadata(
                    template_id=template_id,
                    category_slug=category_slug,
                    category=CATEGORY_SLUG_MAP.get(category_slug, category),
                    topic=topic.strip(),
                    topic_slug=topic_slug,
                    duration_min=duration_min,
                )
                doc = TemplateDocument(
                    metadata=meta,
                    body=body.strip(),
                    file_path=str(md_file),
                )
                self._by_id[template_id] = doc
                self._by_topic_lower[topic.strip().lower()] = doc
        return len(self._by_id)

    def list_topics(self, category_slug: str | None = None) -> list[TopicMetadata]:
        """Return all indexed topics, optionally filtered by `category_slug`."""
        items = [doc.metadata for doc in self._by_id.values()]
        if category_slug:
            items = [m for m in items if m.category_slug == category_slug]
        return items

    def get(self, template_id_or_topic: str) -> TemplateDocument | None:
        """Look up a template by its `template_id` or case-insensitive `topic` title."""
        key = template_id_or_topic.strip()
        if key in self._by_id:
            return self._by_id[key]
        return self._by_topic_lower.get(key.lower())

