"""WP-B0 (Member 1): Template Store and Template Linter.

Responsibilities (Brief §5.3, §5.4):
- Load markdown templates from `data/templates/<category_slug>/<topic_slug>.md`
- Validate frontmatter (`topic`, `category`, `duration_min` in {5, 10, 15, 20})
- Index templates by `template_id` ("<category_slug>/<topic_slug>") and topic name
- Provide `list_topics()` for `GET /api/topics`
- Provide `lint_template_file()` for pytest validation of the 600-template repository
"""

import re
from pathlib import Path

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


def slugify_topic(topic: str) -> str:
    """Convert a topic title into a clean snake_case slug (Brief §5.3)."""
    cleaned = re.sub(r"[^a-z0-9\s_]", "", topic.lower())
    return re.sub(r"[\s_]+", "_", cleaned).strip("_")


def lint_template_file(file_path: Path) -> list[str]:
    """Validate a single template `.md` file against Brief §5.3 conventions.

    TODO (Member 1 - WP-B0):
    1. Check frontmatter keys (`topic`, `category`, `duration_min`).
    2. Check `duration_min` is in (5, 10, 15, 20).
    3. Check slot syntax (`{{ argument_<name> }}`), uniqueness, and slot counts.
    4. Check no markdown headers (`# `) remain in body.
    """
    issues: list[str] = []
    if not file_path.exists():
        return [f"File does not exist: {file_path}"]
    raw = file_path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        issues.append(
            "Invalid or out-of-order YAML frontmatter (expected topic, category, duration_min)."
        )
        return issues
    _, _, duration_str, body = match.groups()
    if int(duration_str) not in VALID_DURATIONS:
        issues.append(f"Invalid duration_min: {duration_str} (expected 5, 10, 15, or 20).")
    if not body.strip():
        issues.append("Template body is empty.")
    return issues


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

