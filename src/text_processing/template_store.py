"""WP-B0 (Member 1): Template Store and Template Linter.

Responsibilities (Brief §5.3, §5.4):
- Load markdown templates from `data/templates/<category_slug>/<topic_slug>_<duration>m.md`
- Validate frontmatter (`topic`, `category`, `duration_min` in {5, 10, 15, 20})
- Index templates by `template_id` ("<category_slug>/<topic_slug>") and topic name
- Provide `list_topics()` for `GET /api/topics`
- Provide `lint_template_file()` for pytest validation of the 600-template repository
"""

import logging
import re
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .contracts import CATEGORY_SLUG_MAP, VALID_DURATIONS, TemplateDocument, TopicMetadata

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "data" / "templates"
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
_UNESCAPE_RE = re.compile(r'\\(["\\])')
_HEADING_RE = re.compile(r"#{1,6}(?:[ \t]|$)")
_SUFFIX_RE = re.compile(r"_([0-9]{1,9})m\Z")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")

Severity = Literal["error", "warning"]
# These make a file unusable or let `{{ }}` leak into a script; content-quality rules do not block.
BLOCKING_RULES = frozenset(
    {
        "file_not_found",
        "encoding",
        "frontmatter_format",
        "unknown_category_dir",
        "category_mismatch",
        "duration_invalid",
        "topic_empty",
        "body_empty",
        "slot_syntax",
    }
)


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
    """Slugify a topic (D-15): lowercase, drop apostrophes, non-[a-z0-9] runs become `_`."""
    lowered = topic.casefold().replace("'", "").replace("’", "")
    return _NON_SLUG_RE.sub("_", lowered).strip("_")


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


def lint_template_text(
    raw: str, *, category_slug: str, path: str = "", file_stem: str | None = None
) -> list[LintIssue]:
    """Lint one template's text against Brief §5.3; with `file_stem`, also D-15 file naming."""

    def issue(rule: str, msg: str, line: int | None = None, sev: Severity = "error") -> LintIssue:
        return LintIssue(rule, sev, msg, path, line)

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

    if file_stem is not None:
        suffix = _SUFFIX_RE.search(file_stem)
        if suffix is None or suffix.group(1) != str(tpl.duration_min):
            out.append(issue("duration_suffix_mismatch", "File name must end with _<duration>m."))
        slug_part = file_stem[: suffix.start()] if suffix else file_stem
        if tpl.topic.strip() and slug_part != slugify_topic(tpl.topic):
            out.append(issue("filename_slug", "File name differs from topic slug.", sev="warning"))
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
    except OSError:
        return [LintIssue("file_not_found", "error", "File could not be read.", rel)]
    return lint_template_text(
        raw, category_slug=file_path.parent.name, path=rel, file_stem=file_path.stem
    )


def _iter_template_files(templates_dir: Path) -> list[Path]:
    if not templates_dir.is_dir():
        return []
    return [
        md
        for category_dir in sorted(templates_dir.iterdir())
        if category_dir.is_dir()
        for md in sorted(category_dir.glob("*.md"))
        if md.is_file()
    ]


def lint_corpus(templates_dir: Path) -> list[LintIssue]:
    """Lint every template, then flag topics repeated across files (case-insensitive)."""
    issues: list[LintIssue] = []
    first_seen: dict[str, str] = {}
    for md_file in _iter_template_files(templates_dir):
        issues.extend(lint_template_file(md_file, templates_dir))
        rel = md_file.relative_to(templates_dir).as_posix()
        try:
            topic = parse_front_matter(read_template_text(md_file)).topic.strip().lower()
        except (TemplateFormatError, UnicodeDecodeError, OSError):
            continue
        if topic and topic in first_seen:
            msg = f"Topic already used by {first_seen[topic]}."
            issues.append(LintIssue("topic_duplicate", "error", msg, rel, 2))
        elif topic:
            first_seen[topic] = rel
    return issues


class TemplateStore:
    """In-memory index of markdown script templates loaded at startup (Brief §5.4)."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        self.templates_dir = templates_dir or DEFAULT_TEMPLATES_DIR
        self._by_id: dict[str, TemplateDocument] = {}
        self._by_topic_lower: dict[str, TemplateDocument] = {}
        self.load_issues: list[LintIssue] = []

    def load(self) -> int:
        """Index every usable template and return how many were loaded.

        A file with any lint issue in `BLOCKING_RULES` is skipped. Every finding, including
        non-blocking ones of loaded files, is kept in `self.load_issues`. When two files share a
        topic, the first in traversal order wins the topic lookup.
        """
        self._by_id.clear()
        self._by_topic_lower.clear()
        self.load_issues = []
        skipped = 0
        for md_file in _iter_template_files(self.templates_dir):
            issues = lint_template_file(md_file, self.templates_dir)
            self.load_issues.extend(issues)
            if any(i.rule in BLOCKING_RULES for i in issues):
                skipped += 1
                continue
            try:
                parsed = parse_front_matter(read_template_text(md_file))
            except (TemplateFormatError, UnicodeDecodeError, OSError):
                skipped += 1  # the file changed between the lint read and this read
                continue
            category_slug = md_file.parent.name
            template_id = f"{category_slug}/{md_file.stem}"
            meta = TopicMetadata(
                template_id=template_id,
                category_slug=category_slug,
                category=CATEGORY_SLUG_MAP[category_slug],
                topic=parsed.topic.strip(),
                topic_slug=md_file.stem,
                duration_min=parsed.duration_min,
            )
            doc = TemplateDocument(meta, parsed.body.strip(), str(md_file))
            self._by_id[template_id] = doc
            first = self._by_topic_lower.setdefault(meta.topic.lower(), doc)
            if first is not doc:
                msg = f"Topic already used by {first.metadata.template_id}."
                rel = md_file.relative_to(self.templates_dir).as_posix()
                self.load_issues.append(LintIssue("topic_duplicate", "error", msg, rel, 2))
        logger.info("Template store: loaded %d, skipped %d", len(self._by_id), skipped)
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

