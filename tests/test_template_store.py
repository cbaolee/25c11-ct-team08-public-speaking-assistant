"""Template linter and front matter parser (Brief §5.3, Issue #7)."""

import os
from pathlib import Path

import pytest

from src.text_processing import template_store
from src.text_processing.contracts import CATEGORY_SLUG_MAP
from src.text_processing.template_store import (
    BLOCKING_RULES,
    LintIssue,
    TemplateFormatError,
    TemplateStore,
    lint_corpus,
    lint_template_file,
    parse_front_matter,
    slugify_topic,
)

FRONT = 'topic: "Big Cats"\ncategory: "Wildlife"\nduration_min: 5'
BODY = "Hello {{ argument_one }} and {{ argument_two }}.\n"
REAL_DIR = Path(__file__).resolve().parents[1] / "data" / "templates"


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
    issues = _lint(tmp_path, front=_front(duration=duration), stem=f"big_cats_{duration}m")
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


@pytest.mark.parametrize(
    ("topic", "slug"),
    [
        ("Half-Earth", "half_earth"),
        ("Madagascar's", "madagascars"),
        ("Men’s Health", "mens_health"),
        ("  __A -- B,  C!! d__ ", "a_b_c_d"),
    ],
)
def test_slugify_topic(topic: str, slug: str) -> None:
    assert slugify_topic(topic) == slug


def test_filename_rules_follow_d15(tmp_path: Path) -> None:
    assert _lint(tmp_path, stem="big_cats_5m") == []
    slug = _lint(tmp_path, stem="lions_5m")
    assert [(i.rule, i.severity) for i in slug] == [("filename_slug", "warning")]
    for stem in ("big_cats_10m", "big_cats", "big_cats_05m"):
        issues = _lint(tmp_path, stem=stem)
        assert [(i.rule, i.severity) for i in issues] == [("duration_suffix_mismatch", "error")]


def test_lint_corpus_flags_duplicate_topics_case_insensitively(tmp_path: Path) -> None:
    _write(tmp_path, "wildlife", "big_cats_10m", _front(duration="10"))
    _write(tmp_path, "wildlife", "big_cats_5m", _front(topic='"BIG cats"'))
    dup = [i for i in lint_corpus(tmp_path) if i.rule == "topic_duplicate"]
    assert [(i.path, i.line, i.severity) for i in dup] == [("wildlife/big_cats_5m.md", 2, "error")]
    assert lint_corpus(tmp_path / "missing") == []


def test_store_skips_blocking_files_and_records_issues(tmp_path: Path) -> None:
    _write(tmp_path, "wildlife", "big_cats_5m")
    _write(tmp_path, "wildlife", "bad_5m", _front().replace("category", "Category"))
    _write(tmp_path, "zoology", "big_cats_5m")
    store = TemplateStore(tmp_path)
    assert store.load() == 1
    found = {(i.rule, i.path) for i in store.load_issues}
    assert found == {
        ("frontmatter_format", "wildlife/bad_5m.md"),
        ("unknown_category_dir", "zoology/big_cats_5m.md"),
    }


def test_store_loads_quality_problems_but_records_them(tmp_path: Path) -> None:
    quality = "A {{ argument_x }} B {{ argument_x }}.\n## Heading\n"
    _write(tmp_path, "wildlife", "big_cats_10m", body=quality)
    store = TemplateStore(tmp_path)
    assert store.load() == 1
    doc = store.get("wildlife/big_cats_10m")
    assert doc is not None and doc.metadata.duration_min == 5
    assert {i.rule for i in store.load_issues} == {
        "argument_slot_repeated",
        "markdown_heading",
        "duration_suffix_mismatch",
    }


def test_store_keeps_first_file_for_duplicate_topic(tmp_path: Path) -> None:
    _write(tmp_path, "wildlife", "a_big_cats_5m")
    _write(tmp_path, "wildlife", "b_big_cats_5m", _front(topic='"BIG cats"'))
    store = TemplateStore(tmp_path)
    assert store.load() == 2
    doc = store.get("big cats")
    assert doc is not None and doc.metadata.template_id == "wildlife/a_big_cats_5m"
    dups = [i for i in store.load_issues if i.rule == "topic_duplicate"]
    assert [(i.path, i.line) for i in dups] == [("wildlife/b_big_cats_5m.md", 2)]
    assert "wildlife/a_big_cats_5m" in dups[0].message and "big cats" not in dups[0].message.lower()
    assert len(store.list_topics()) == 2 and store.get("wildlife/b_big_cats_5m") is not None
    _write(tmp_path, "wildlife", "c_big_cats_5m", _front(topic='"big CATS"'))
    assert store.load() == 3
    assert sum(i.rule == "topic_duplicate" for i in store.load_issues) == 2


def test_directory_named_like_a_template_is_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "wildlife", "big_cats_5m")
    (tmp_path / "wildlife" / "x.md").mkdir()
    assert lint_corpus(tmp_path) == []
    store = TemplateStore(tmp_path)
    assert store.load() == 1 and store.load_issues == []


@pytest.mark.parametrize("ok_reads", [0, 1])
def test_unreadable_file_is_skipped_not_fatal(tmp_path: Path, monkeypatch, ok_reads: int) -> None:
    _write(tmp_path, "wildlife", "big_cats_5m")
    bad = _write(tmp_path, "wildlife", "lions_5m", _front(topic='"Lions"'))
    real, calls = template_store.read_template_text, []

    def flaky(path: Path) -> str:
        if path == bad:
            calls.append(path)
            if len(calls) > ok_reads:
                raise PermissionError
        return real(path)

    monkeypatch.setattr(template_store, "read_template_text", flaky)
    expected = {"file_not_found"} if ok_reads == 0 else set()
    issues = lint_template_file(bad, tmp_path)
    assert {i.rule for i in issues} == expected
    assert all(i.message == "File could not be read." for i in issues)
    calls.clear()
    assert {i.rule for i in lint_corpus(tmp_path)} == expected
    calls.clear()
    store = TemplateStore(tmp_path)
    assert store.load() == 1 and store.get("wildlife/lions_5m") is None
    assert {i.rule for i in store.load_issues} == expected


def test_store_get_and_list_topics(tmp_path: Path) -> None:
    _write(tmp_path, "wildlife", "big_cats_5m")
    _write(tmp_path, "sports", "warm_up_10m", _front('"Warm Up"', '"Sports"', "10"))
    store = TemplateStore(tmp_path)
    store.load()
    assert {m.template_id for m in store.list_topics()} == {
        "wildlife/big_cats_5m",
        "sports/warm_up_10m",
    }
    only = store.list_topics(category_slug="sports")
    assert [(m.category, m.duration_min) for m in only] == [("Sports", 10)]
    by_id, by_topic = store.get("wildlife/big_cats_5m"), store.get("  big CATS ")
    assert by_id is not None and by_id is by_topic and by_id.body == BODY.strip()
    assert store.get("missing") is None


def test_store_missing_directory_returns_zero(tmp_path: Path) -> None:
    store = TemplateStore(tmp_path / "nope")
    assert store.load() == 0 and store.list_topics() == [] and store.load_issues == []


def test_loader_loads_a_file_exactly_when_it_has_no_blocking_issue(tmp_path: Path) -> None:
    good = f"---\n{FRONT}\n---\n{BODY}"
    samples = {
        "plain": good,
        "bom_crlf": "\N{ZERO WIDTH NO-BREAK SPACE}" + good.replace("\n", "\r\n"),
        "trailing_ws": good.replace("\n", "  \n", 5),
        "escaped": good.replace('"Big Cats"', '"The \\"Big\\" Cats"'),
        "upper_key": good.replace("category", "Category"),
    }
    for name, text in samples.items():
        (tmp_path / "wildlife").mkdir(exist_ok=True)
        (tmp_path / "wildlife" / f"{name}.md").write_bytes(text.encode("utf-8"))
    store = TemplateStore(tmp_path)
    store.load()
    for name in samples:
        issues = lint_template_file(tmp_path / "wildlife" / f"{name}.md", tmp_path)
        blocked = any(i.rule in BLOCKING_RULES for i in issues)
        assert (store.get(f"wildlife/{name}") is not None) == (not blocked), name
    assert store.get("wildlife/upper_key") is None and store.get("wildlife/escaped") is not None


@pytest.mark.skipif(not REAL_DIR.is_dir(), reason="data/templates not present")
def test_lint_corpus_smoke_on_real_templates() -> None:
    assert isinstance(lint_corpus(REAL_DIR), list)


@pytest.mark.skipif(os.environ.get("RUN_TEMPLATE_LINT") != "1", reason="set RUN_TEMPLATE_LINT=1")
def test_real_templates_have_no_lint_errors() -> None:
    errors = [i for i in lint_corpus(REAL_DIR) if i.severity == "error"]
    assert not errors, "\n".join(f"{i.path}:{i.line} {i.rule}" for i in errors[:50])
