"""Template linter and front matter parser (Brief §5.3, Issue #7)."""

from pathlib import Path

import pytest

from src.text_processing.contracts import CATEGORY_SLUG_MAP
from src.text_processing.template_store import (
    LintIssue,
    TemplateFormatError,
    lint_template_file,
    parse_front_matter,
)

FRONT = 'topic: "Big Cats"\ncategory: "Wildlife"\nduration_min: 5'
BODY = "Hello {{ argument_one }} and {{ argument_two }}.\n"


def _write(tmp_path: Path, category_dir: str, stem: str, front: str = FRONT, body: str = BODY):
    path = tmp_path / category_dir / f"{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}\n---\n{body}", encoding="utf-8", newline="\n")
    return path


def _rules(issues: list[LintIssue], severity: str | None = None) -> list[str]:
    return [i.rule for i in issues if severity in (None, i.severity)]


def _lint(tmp_path: Path, body: str = BODY, front: str = FRONT, stem: str = "big_cats_5m"):
    return lint_template_file(_write(tmp_path, "wildlife", stem, front, body), tmp_path)


def test_parse_front_matter_valid() -> None:
    parsed = parse_front_matter(f"---\n{FRONT}\n---\n\n{BODY}")
    assert (parsed.topic, parsed.category, parsed.duration_min) == ("Big Cats", "Wildlife", 5)
    assert parsed.body_start_line == 6 and BODY.strip() in parsed.body


def test_valid_file_has_no_issues(tmp_path: Path) -> None:
    assert _lint(tmp_path) == []


def _front(topic: str = '"Big Cats"', category: str = '"Wildlife"', duration: str = "5") -> str:
    return f"topic: {topic}\ncategory: {category}\nduration_min: {duration}"


@pytest.mark.parametrize(
    ("front", "line"),
    [
        (_front().replace("category", "Category"), 3),
        ('category: "Wildlife"\ntopic: "Big Cats"\nduration_min: 5', 2),
        ('topic: "Big Cats"\nduration_min: 5', 3),
        (FRONT + '\nextra: "x"', 5),
        (_front(topic="Big Cats"), 2),
        (_front(duration="5.5"), 4),
        (_front(duration='"5"'), 4),
        (_front(duration="-5"), 4),
        (_front(duration="12345678901"), 4),
        (_front(duration="٥"), 4),
        ('# Title\ncategory: "Wildlife"\nduration_min: 5', 2),
    ],
)
def test_bad_front_matter_is_rejected(tmp_path: Path, front: str, line: int) -> None:
    issues = _lint(tmp_path, front=front)
    assert [(i.rule, i.line) for i in issues] == [("frontmatter_format", line)]


def test_empty_and_unterminated_files_are_rejected() -> None:
    for raw in ("", "---\n", f"---\n{FRONT}\n"):
        with pytest.raises(TemplateFormatError) as exc:
            parse_front_matter(raw)
        assert exc.value.rule == "frontmatter_format"


def test_topic_with_escaped_quote_and_backslash() -> None:
    raw = '---\ntopic: "The \\"Big\\" \\\\ Cats"\ncategory: "Wildlife"\nduration_min: 5\n---\nx'
    assert parse_front_matter(raw).topic == 'The "Big" \\ Cats'


def test_crlf_and_bom_are_accepted_and_keep_line_numbers(tmp_path: Path) -> None:
    path = tmp_path / "wildlife" / "big_cats_5m.md"
    path.parent.mkdir()
    text = f"---\n{FRONT}\n---\n{BODY}".replace("\n", "\r\n")
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    assert lint_template_file(path, tmp_path) == []
    text = f"---\n{FRONT}\n---\nOne.\n\n## Heading\n".replace("\n", "\r\n")
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    assert [(i.rule, i.line) for i in lint_template_file(path, tmp_path)] == [
        ("markdown_heading", 8)
    ]


def test_non_utf8_file_is_an_encoding_error(tmp_path: Path) -> None:
    path = tmp_path / "wildlife" / "big_cats_5m.md"
    path.parent.mkdir()
    path.write_bytes(b'---\ntopic: "Caf\xe9"\n')
    assert _rules(lint_template_file(path, tmp_path)) == ["encoding"]


@pytest.mark.parametrize("slug", sorted(CATEGORY_SLUG_MAP))
def test_category_must_match_directory(tmp_path: Path, slug: str) -> None:
    path = _write(tmp_path, slug, "big_cats_5m", _front(category=f'"{CATEGORY_SLUG_MAP[slug]}"'))
    assert lint_template_file(path, tmp_path) == []
    wrong = _write(tmp_path, slug, "big_cats_5m", _front(category='"Other"'))
    assert [(i.rule, i.line) for i in lint_template_file(wrong, tmp_path)] == [
        ("category_mismatch", 3)
    ]


def test_unknown_category_dir(tmp_path: Path) -> None:
    odd = lint_template_file(_write(tmp_path, "zoology", "big_cats_5m"), tmp_path)
    assert _rules(odd) == ["unknown_category_dir"]


@pytest.mark.parametrize("duration", ["0", "7", "25"])
def test_duration_must_be_in_allowed_set(tmp_path: Path, duration: str) -> None:
    issues = _lint(tmp_path, front=_front(duration=duration))
    assert [(i.rule, i.line) for i in issues] == [("duration_invalid", 4)]


@pytest.mark.parametrize(
    "body",
    [
        "Hi {{ Argument_x }}.",
        "Hi {{ a b }}.",
        "Hi {{ argument_x }.",
        "Hi }} there.",
        "Hi {{ }}.",
        "Hi {{{ argument_x }}.",
        "Hi {{ argument_x }}}.",
        "Hi {{{ argument_x }}}.",
    ],
)
def test_bad_slot_syntax(tmp_path: Path, body: str) -> None:
    issues = _lint(tmp_path, body=body)
    assert [(i.rule, i.line) for i in issues] == [("slot_syntax", 6)]


@pytest.mark.parametrize(
    "body", ["Use {a} here.", "{{ argument_a }}{{ argument_b }}", "{{\nargument_x\n}} ok."]
)
def test_valid_slot_forms_are_accepted(tmp_path: Path, body: str) -> None:
    assert _lint(tmp_path, body=body) == []


def test_repeated_argument_slot_is_error_but_entity_slot_may_repeat(tmp_path: Path) -> None:
    two = "A {{ argument_x }}.\n\nB {{ argument_x }}.\n"
    issue = _lint(tmp_path, body=two)[0]
    assert (issue.rule, issue.line) == ("argument_slot_repeated", 8)
    thrice = _lint(tmp_path, body=two + "C {{ argument_x }}.\n")
    assert [(i.rule, i.line) for i in thrice] == [("argument_slot_repeated", 8)]
    assert _lint(tmp_path, body="{{ lion }} and {{ lion }} with {{ argument_x }}.") == []


def test_markdown_heading_is_error_but_mid_line_hash_is_not(tmp_path: Path) -> None:
    issues = _lint(tmp_path, body="Intro\n## Title\n")
    assert [(i.rule, i.line) for i in issues] == [("markdown_heading", 7)]
    assert _lint(tmp_path, body="Rank #1 and C# are fine. #hashtag\n") == []


def test_empty_body_and_empty_topic(tmp_path: Path) -> None:
    assert _rules(_lint(tmp_path, body="  \n")) == ["body_empty"]
    issues = _lint(tmp_path, front=_front(topic='" "'), stem="x_5m")
    assert [(i.rule, i.line) for i in issues] == [("topic_empty", 2)]


def test_lint_template_file_returns_lint_issues_and_handles_missing_file(tmp_path: Path) -> None:
    issues = _lint(tmp_path, body="## Title\n")
    assert issues and all(isinstance(i, LintIssue) for i in issues)
    assert (issues[0].severity, issues[0].path) == ("error", "wildlife/big_cats_5m.md")
    missing = lint_template_file(tmp_path / "wildlife" / "nope.md", tmp_path)
    assert [(i.rule, i.path) for i in missing] == [("file_not_found", "wildlife/nope.md")]
