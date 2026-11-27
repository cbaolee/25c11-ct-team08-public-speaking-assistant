"""Hybrid 2-layer classifier separating citable speech source material from chat.

Categories & Decision Rule (documented in ``docs/citation_policy.md``):
1. ``source_material`` (``citable=True``):
   Facts, statistics, dates/timelines, named studies/reports, direct quotes,
   taxonomic/technical descriptions, concrete case studies, or structured evidence notes
   supplied by the user as material for the speech.
2. ``editing_instruction`` (``citable=False``):
   Directives controlling length, tone, pacing, structure, or topic framing
   (e.g. "make it shorter", "use a more dramatic tone", "focus on the conclusion").
   Kept in ``chat_context`` / ``user_feedback`` so the LLM obeys them, never cited.
3. ``casual_chat`` (``citable=False``):
   Greetings, acknowledgements, emotional small-talk, or conversational remarks
   (e.g. "I'm happy", "thanks!", "sounds good", "I feel nervous today"). Never cited.

Uploaded files (``.pdf``, ``.md``, ``.txt``) bypass this classifier and are always
treated as citable source documents.

For multi-sentence or multi-line messages that mix instructions/pleasantries with
factual notes, ``extract_citable_source_text`` filters at the sentence/block level so
only ``source_material`` segments enter ``DocumentChunk(page=0)``.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np

from src.app.constants import CONSTANTS

from .retrieval import SemanticRetriever

if TYPE_CHECKING:
    from numpy.typing import NDArray

SourceCategory = Literal["source_material", "editing_instruction", "casual_chat"]
ClassifierLayer = Literal["deterministic", "semantic", "fallback"]

_MIN_WORDS = int(CONSTANTS["script"].get("source_classifier_min_words", 6))
_SEMANTIC_MIN_SCORE = float(
    CONSTANTS["script"].get("source_classifier_semantic_min_score", 0.38)
)
_SEMANTIC_MARGIN = float(CONSTANTS["script"].get("source_classifier_semantic_margin", 0.05))

_AUTO_REGEN_PREFIX = "write a fresh variation of this speech"

# ---------------------------------------------------------------------------
# Layer 1 deterministic patterns
# ---------------------------------------------------------------------------

_CASUAL_EXACT = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hey there",
        "hello there",
        "good morning",
        "good afternoon",
        "good evening",
        "thanks",
        "thank you",
        "thank you so much",
        "thanks a lot",
        "many thanks",
        "thx",
        "ty",
        "ok",
        "okay",
        "k",
        "kk",
        "sure",
        "yes",
        "yep",
        "yeah",
        "no",
        "nope",
        "got it",
        "understood",
        "makes sense",
        "sounds good",
        "sounds great",
        "looks good",
        "looks great",
        "that looks good",
        "that sounds great",
        "awesome",
        "great",
        "great job",
        "good job",
        "well done",
        "nice",
        "nice work",
        "cool",
        "perfect",
        "amazing",
        "love it",
        "i love it",
        "i like it",
        "i like this",
        "bye",
        "goodbye",
        "done",
        "generate",
        "ready",
        "let's go",
        "lets go",
    }
)

_CASUAL_PATTERN = re.compile(
    r"^(?:"
    r"(?:hi|hello|hey|yo|greetings)\b[\s,!.]*|"
    r"(?:thanks|thank\s+you|appreciate\s+it)\b[^0-9]*|"
    r"i(?:'m|\s+am|\s+feel|\s+felt)\s+(?:so\s+|very\s+|really\s+|pretty\s+|quite\s+|a\s+bit\s+)?"
    r"(?:happy|glad|excited|nervous|anxious|worried|tired|sad|bored|ready|confused|grateful|proud|fine|good|great|okay)\b[^0-9]*|"
    r"(?:that|this)\s+(?:is|was|makes\s+me)\s+(?:so\s+|very\s+|really\s+)?"
    r"(?:happy|great|awesome|cool|funny|nice|helpful|sweet|amazing)\b[^0-9]*|"
    r"(?:can|could|would)\s+you\s+help\s+me(?:\s+with\s+this|\s+practice)?\s*\??|"
    r"(?:what\s+do\s+you\s+think|how\s+are\s+you|are\s+you\s+there|what\s+now)\s*\??|"
    r"i\s+(?:don't|do\s+not)\s+know\s+what\s+to\s+(?:say|write|add)\b[^0-9]*"
    r")$",
    re.IGNORECASE,
)

_EDITING_IMPERATIVE_PATTERN = re.compile(
    r"^(?:(?:please|kindly|can\s+you|could\s+you|would\s+you|try\s+to|let's|lets)\s+)?"
    r"(?:"
    r"make\s+(?:it|this|the\s+\w+)\b|"
    r"keep\s+(?:it|this|the\s+\w+)\b|"
    r"(?:shorten|lengthen|expand|condense|trim|cut|simplify|rewrite|revise|rephrase|reword|polish|regenerate|redo)\b|"
    r"change\s+(?:the\s+)?(?:tone|style|pacing|opening|intro|introduction|ending|conclusion|hook|structure|wording|greeting)\b|"
    r"use\s+(?:a\s+|an\s+)?(?:more\s+|less\s+)?(?:formal|informal|casual|conversational|academic|dramatic|inspiring|friendly|simple|simpler|professional|humorous|serious|warm|energetic)\b|"
    r"(?:sound|be)\s+(?:more|less)\s+\w+|"
    r"add\s+(?:a\s+|an\s+|some\s+|more\s+)?(?:joke|humor|humour|hook|rhetorical\s+question|pause|transition|transitions|call\s+to\s+action|greeting|closing|story|metaphor|energy|passion)\b|"
    r"(?:remove|drop|delete|avoid|skip)\s+(?:the\s+)?(?:jargon|fluff|repetition|greeting|cliches|clichés|first\s+paragraph|last\s+paragraph)\b|"
    r"(?:focus|concentrate|emphasize|dwell)\s+(?:more\s+)?on\b|"
    r"(?:talk|speak|write)\s+(?:more\s+)?about\b|"
    r"(?:more|less)\s+(?:formal|casual|dramatic|concise|brief|energetic|emotional|persuasive|academic)\b|"
    r"too\s+(?:long|short|wordy|formal|casual|stiff|boring|academic|complex|fast|slow)\b"
    r")",
    re.IGNORECASE,
)

# Leading directive prefix that may introduce a real fact in a mixed sentence:
# e.g. "Also mention that the Saola was discovered in 1992..."
_FACT_INTRO_WRAPPER = re.compile(
    r"^(?:(?:also|and|please|can\s+you|could\s+you)\s+)*"
    r"(?:mention|include|note|state|cite|say|add|highlight|point\s+out)\s+"
    r"(?:that|the\s+fact\s+that)\s+",
    re.IGNORECASE,
)

_YEAR_RE = re.compile(r"\b(?:1[5-9]\d{2}|20\d{2})\b")
_QUANT_RE = re.compile(
    r"(?:[$€£]\s*\d+(?:[.,]\d+)?)|"
    r"(?:\b\d+(?:[.,]\d+)?\s*(?:%|percent|percentage|million|billion|trillion|thousand|"
    r"km|kilometers|meters|m|cm|mm|kg|grams|tons|tonnes|lbs|miles|acres|hectares|"
    r"years|months|weeks|days|hours|minutes|seconds|degrees|celsius|fahrenheit|"
    r"species|individuals|participants|patients|respondents|cases|countries|cities|"
    r"mw|gw|kw|kwh|gb|tb|mb|fps|hz|db|x|fold)\b)",
    re.IGNORECASE,
)
_ATTRIBUTION_RE = re.compile(
    r"\b(?:according\s+to|study|studies|report|reported|research|researchers|survey|"
    r"published\s+in|journal|university|institute|ministry|organization|agency|census|"
    r"meta-analysis|clinical\s+trial|experiment|dataset|evidence\s+shows|data\s+shows|"
    r"found\s+that|discovered\s+in|documented\s+in|estimated\s+at|recorded\s+in|"
    r"classified\s+as|distinguished\s+by|characterized\s+by|native\s+to|endemic\s+to|"
    r"historically\s+found|correlates\s+with|caused\s+by|resulted\s+in)\b",
    re.IGNORECASE,
)
_CITATION_PAREN_RE = re.compile(r"\([A-Z][A-Za-z\-]+(?:\s+et\s+al\.)?,?\s*(?:19|20)\d{2}\)")
_QUOTE_FACT_RE = re.compile(r'"[^"]{20,}"')

# ---------------------------------------------------------------------------
# Layer 2 semantic prototypes (encoded lazily once per process)
# ---------------------------------------------------------------------------

_SOURCE_PROTOTYPES: tuple[str, ...] = (
    (
        "According to a 2022 peer-reviewed study, global coral reef cover "
        "declined by 50 percent since 1950."
    ),
    (
        "The species is a nocturnal mammal native to tropical mountain "
        "forests and distinguished by long horns."
    ),
    (
        "Empirical survey data from 1,400 hospital patients showed a "
        "34 percent reduction in recovery time."
    ),
    (
        "Historically, the treaty was signed in 1973 and established "
        "legal conservation zones across three regions."
    ),
    (
        "Researchers at the university institute measured carbon emissions "
        "at 4.2 million tonnes per year."
    ),
    (
        "Case study: after the city expanded protected bike lanes, "
        "commuter injuries dropped by 28 percent."
    ),
    (
        "Its primary mechanism relies on chemosynthetic bacteria converting "
        "hydrogen sulfide into organic matter."
    ),
    (
        "Critics argue that battery supply chains face lithium shortages "
        "and high water consumption in arid mines."
    ),
    (
        "Key findings: mainland populations went extinct due to competition "
        "from invasive predators and habitat loss."
    ),
    (
        "Economic reports estimate the annual infrastructure budget at "
        "12 billion dollars across rural provinces."
    ),
)

_INSTRUCTION_PROTOTYPES: tuple[str, ...] = (
    "Please make the speech shorter and easier to read aloud.",
    "Change the tone to be warmer, more conversational, and inspiring.",
    "Add a dramatic opening hook and a memorable call to action at the end.",
    "Rewrite the second paragraph so it flows more smoothly without technical jargon.",
    "Focus more on the practical implications for students and keep sentences brief.",
    "Make the introduction punchier and cut repetitive transitions.",
    "Use a more formal academic style suitable for a keynote conference.",
    "Can you simplify the conclusion and make it sound more energetic?",
)

_CASUAL_PROTOTYPES: tuple[str, ...] = (
    "I am really happy today and excited to practice my presentation!",
    "Thank you so much, that looks great to me!",
    "Hello there, how are you doing this morning?",
    "Okay sounds good, let us go ahead with that.",
    "I feel a little nervous about speaking in front of my class tomorrow.",
    "Awesome job, I really love how this turned out!",
    "I am not sure what else to say right now, what do you think?",
    "Great, thanks for helping me prepare!",
)

_proto_lock = threading.Lock()
_proto_cache: dict[str, NDArray[np.float32]] | None = None
_proto_model_id: int | None = None


@dataclass(frozen=True)
class SourceClassification:
    """Classification outcome for a user message or sentence."""

    category: SourceCategory
    citable: bool
    layer: ClassifierLayer
    reason: str
    scores: dict[str, float] = field(default_factory=dict)


def _normalize_for_match(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned.rstrip(".!? ").lower()


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+(?:'[a-zA-Z]+)?", text)


def _count_factual_signals(text: str) -> int:
    """Count distinct types/occurrences of concrete factual or evidentiary markers."""
    signals = 0
    signals += min(2, len(_YEAR_RE.findall(text)))
    signals += min(2, len(_QUANT_RE.findall(text)))
    signals += min(2, len(_ATTRIBUTION_RE.findall(text)))
    if _CITATION_PAREN_RE.search(text):
        signals += 2
    if _QUOTE_FACT_RE.search(text):
        signals += 1
    # Multi-line structured note (e.g. heading + bullets / enumerated facts)
    non_empty_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(non_empty_lines) >= 3:
        signals += 1
    return signals


def _has_third_person_descriptive_structure(text: str, words: list[str]) -> bool:
    """Heuristic for encyclopedic/descriptive factual statements without numbers."""
    if len(words) < 10:
        return False
    low_words = {w.lower() for w in words}
    first_second_pronouns = {"i", "i'm", "ive", "i've", "me", "my", "you", "your", "please"}
    if low_words & first_second_pronouns:
        return False
    descriptive_verbs = {
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "survives",
        "survived",
        "lives",
        "lived",
        "occurs",
        "occurred",
        "depends",
        "relies",
        "causes",
        "caused",
        "reduces",
        "reduced",
        "increases",
        "increased",
        "produces",
        "contains",
        "consists",
        "correlates",
        "demonstrates",
        "indicates",
        "remains",
    }
    return bool(low_words & descriptive_verbs)


def _get_prototype_embeddings(
    retriever: SemanticRetriever,
) -> dict[str, NDArray[np.float32]] | None:
    """Encode anchor prototypes once per model instance."""
    global _proto_cache, _proto_model_id
    model = retriever.get_model()
    if model is None:
        return None
    # Detect lightweight hash-based test mocks so we don't rely on English prototype vectors
    if type(model).__name__.startswith("Mock"):
        return None

    mid = id(model)
    if _proto_cache is not None and _proto_model_id == mid:
        return _proto_cache

    with _proto_lock:
        if _proto_cache is not None and _proto_model_id == mid:
            return _proto_cache
        try:
            _proto_cache = {
                "source_material": retriever._encode(model, list(_SOURCE_PROTOTYPES)),
                "editing_instruction": retriever._encode(model, list(_INSTRUCTION_PROTOTYPES)),
                "casual_chat": retriever._encode(model, list(_CASUAL_PROTOTYPES)),
            }
            _proto_model_id = mid
        except Exception:
            return None
    return _proto_cache


def _top2_mean_similarity(vec: NDArray[np.float32], proto_mat: NDArray[np.float32]) -> float:
    sims = np.sort((proto_mat @ vec).ravel())[::-1]
    if len(sims) == 0:
        return 0.0
    if len(sims) == 1:
        return float(sims[0])
    return float(0.65 * sims[0] + 0.35 * sims[1])


def classify_user_message(
    text: str,
    *,
    retriever: SemanticRetriever | None = None,
    min_words: int = _MIN_WORDS,
    semantic_min_score: float = _SEMANTIC_MIN_SCORE,
    semantic_margin: float = _SEMANTIC_MARGIN,
) -> SourceClassification:
    """Classify a single user message or sentence into source, instruction, or casual chat."""
    if not text or not text.strip():
        return SourceClassification(
            category="casual_chat",
            citable=False,
            layer="deterministic",
            reason="empty_input",
        )

    cleaned = text.strip()
    norm = _normalize_for_match(cleaned)
    if norm.startswith(_AUTO_REGEN_PREFIX):
        return SourceClassification(
            category="editing_instruction",
            citable=False,
            layer="deterministic",
            reason="auto_regenerate_prompt",
        )

    if norm in _CASUAL_EXACT:
        return SourceClassification(
            category="casual_chat",
            citable=False,
            layer="deterministic",
            reason="exact_casual_phrase",
        )

    words = _word_tokens(cleaned)
    word_count = len(words)
    factual_signals = _count_factual_signals(cleaned)

    # Layer 1A: Conversational / emotional statements without factual signals
    if factual_signals == 0 and _CASUAL_PATTERN.match(cleaned):
        return SourceClassification(
            category="casual_chat",
            citable=False,
            layer="deterministic",
            reason="casual_conversational_pattern",
        )

    # Layer 1B: Strip "Also mention that ..." wrapper when checking if core is factual
    unwrapped = _FACT_INTRO_WRAPPER.sub("", cleaned).strip()
    unwrapped_words = _word_tokens(unwrapped)
    unwrapped_facts = _count_factual_signals(unwrapped)
    was_fact_wrapper = unwrapped != cleaned and (
        len(unwrapped_words) >= min_words or unwrapped_facts >= 1
    )

    if not was_fact_wrapper and _EDITING_IMPERATIVE_PATTERN.match(cleaned):
        if factual_signals == 0 or word_count <= 12:
            return SourceClassification(
                category="editing_instruction",
                citable=False,
                layer="deterministic",
                reason="editing_imperative_pattern",
            )

    # Short inputs without concrete numeric/date/study signals cannot be citable source chunks
    if word_count < min_words and factual_signals == 0:
        return SourceClassification(
            category="casual_chat",
            citable=False,
            layer="deterministic",
            reason="below_min_words_without_facts",
        )

    # Layer 1C: Strong factual density or encyclopedic third-person note -> fast accept
    if factual_signals >= 2 or (factual_signals >= 1 and word_count >= 8):
        return SourceClassification(
            category="source_material",
            citable=True,
            layer="deterministic",
            reason="strong_factual_signals",
        )

    if was_fact_wrapper and (
        factual_signals >= 1
        or _has_third_person_descriptive_structure(unwrapped, _word_tokens(unwrapped))
    ):
        return SourceClassification(
            category="source_material",
            citable=True,
            layer="deterministic",
            reason="explicit_fact_inclusion",
        )

    # Layer 2: Semantic prototype scoring with precision-first margin
    active_retriever = retriever or SemanticRetriever()
    protos = _get_prototype_embeddings(active_retriever)
    model = active_retriever.get_model()
    if protos is not None and model is not None:
        try:
            target_text = unwrapped if was_fact_wrapper else cleaned
            vec = active_retriever._encode(model, [target_text])[0]
            s_src = _top2_mean_similarity(vec, protos["source_material"])
            s_ins = _top2_mean_similarity(vec, protos["editing_instruction"])
            s_cas = _top2_mean_similarity(vec, protos["casual_chat"])
            scores = {
                "source_material": round(s_src, 4),
                "editing_instruction": round(s_ins, 4),
                "casual_chat": round(s_cas, 4),
            }
            runner_up = max(s_ins, s_cas)
            if s_src >= semantic_min_score and (s_src - runner_up) >= semantic_margin:
                return SourceClassification(
                    category="source_material",
                    citable=True,
                    layer="semantic",
                    reason="prototype_margin_passed",
                    scores=scores,
                )
            non_src: SourceCategory = "editing_instruction" if s_ins >= s_cas else "casual_chat"
            return SourceClassification(
                category=non_src,
                citable=False,
                layer="semantic",
                reason="prototype_rejected_fail_closed",
                scores=scores,
            )
        except Exception:
            pass

    # Deterministic fallback when embedding model is unavailable or mocked:
    # accept third-person descriptive statements, fail-closed on everything else.
    if _has_third_person_descriptive_structure(cleaned, words):
        return SourceClassification(
            category="source_material",
            citable=True,
            layer="fallback",
            reason="third_person_descriptive_fallback",
        )

    fallback_cat: SourceCategory = (
        "editing_instruction" if _EDITING_IMPERATIVE_PATTERN.search(cleaned) else "casual_chat"
    )
    return SourceClassification(
        category=fallback_cat,
        citable=False,
        layer="fallback",
        reason="fail_closed_fallback",
    )


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_MIXED_CONJUNCTION_SPLIT_RE = re.compile(
    r"(?:,\s+|\s+)(?=(?:and\s+)?(?:also\s+)?(?:mention|include|note|state|cite|say|add|highlight)\s+(?:that|the\s+fact\s+that)\b)",
    re.IGNORECASE,
)
_CONVERSATIONAL_PRONOUNS = frozenset(
    {"i", "i'm", "im", "ive", "i've", "my", "me", "we", "you", "your", "please", "thanks"}
)


def _is_short_heading_line(line: str) -> bool:
    """Detect short section headers like 'Overview' or 'Historically found across:'."""
    stripped = re.sub(r"^[#*\-\s]+", "", line).strip()
    if not stripped or stripped.endswith((".", "!", "?")):
        return False
    words = _word_tokens(stripped)
    if any(w.lower() in _CONVERSATIONAL_PRONOUNS for w in words):
        return False
    is_explicit_header = line.lstrip().startswith("#") or stripped.endswith(":")
    if not is_explicit_header and len(words) > 3:
        return False
    return (
        1 <= len(words) <= 6
        and len(stripped) <= 48
        and _normalize_for_match(stripped) not in _CASUAL_EXACT
    )


def extract_citable_source_text(
    text: str,
    *,
    retriever: SemanticRetriever | None = None,
) -> str | None:
    """Filter a user message at line/sentence granularity, keeping only ``source_material``.

    - Pure casual or pure editing messages return ``None``.
    - Pure source notes (including structured multi-line bullet lists with headers) are
      preserved intact.
    - Mixed messages (e.g. ``"Thanks! Make it shorter. Also mention that the Saola was
      discovered in 1992 in Vu Quang Nature Reserve."``) have casual/editing sentences
      stripped so only factual source sentences become citable chunks.
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    if not lines:
        return None

    # Check if multi-line structured note (e.g. header + short factual list items):
    # If there are >=3 lines without editing/casual lines, evaluate as cohesive block first.
    if len(lines) >= 3:
        whole = classify_user_message(cleaned, retriever=retriever)
        has_casual_or_edit_line = any(
            _CASUAL_PATTERN.match(ln)
            or _normalize_for_match(ln) in _CASUAL_EXACT
            or (_EDITING_IMPERATIVE_PATTERN.match(ln) and not _FACT_INTRO_WRAPPER.match(ln))
            for ln in lines
        )
        if whole.citable and not has_casual_or_edit_line:
            return cleaned

    kept_lines: list[str] = []
    pending_heading: str | None = None
    had_citable_sentence = False

    for line in lines:
        if _is_short_heading_line(line) and len(lines) > 1:
            pending_heading = line
            continue

        # Split multi-sentence lines (and mixed "Make it shorter and mention that ..." clauses)
        raw_sentences: list[str] = []
        for s in _SENTENCE_SPLIT_RE.split(line):
            s = s.strip()
            if not s:
                continue
            sub_parts = [p.strip() for p in _MIXED_CONJUNCTION_SPLIT_RE.split(s) if p.strip()]
            raw_sentences.extend(sub_parts)

        kept_in_line: list[str] = []
        for sent in raw_sentences:
            decision = classify_user_message(sent, retriever=retriever)
            if decision.citable:
                had_citable_sentence = True
                # Clean leading "Also mention that " so the chunk stores clean factual prose
                cleaned_sent = _FACT_INTRO_WRAPPER.sub("", sent).strip()
                if cleaned_sent and cleaned_sent[0].islower():
                    cleaned_sent = cleaned_sent[0].upper() + cleaned_sent[1:]
                kept_in_line.append(cleaned_sent or sent)

        line_words = _word_tokens(line)
        has_conv_pronoun = any(w.lower() in _CONVERSATIONAL_PRONOUNS for w in line_words)
        if kept_in_line:
            if pending_heading is not None:
                kept_lines.append(pending_heading)
                pending_heading = None
            kept_lines.append(" ".join(kept_in_line))
        elif pending_heading is not None and len(line_words) <= 5 and not has_conv_pronoun:
            # Short bullet item under a heading (e.g. "Tasmania", "Papua New Guinea")
            norm_item = _normalize_for_match(line)
            if norm_item not in _CASUAL_EXACT and not _CASUAL_PATTERN.match(line):
                kept_lines.append(pending_heading)
                pending_heading = None
                kept_lines.append(line)
        elif kept_lines and len(line_words) <= 5 and not has_conv_pronoun:
            norm_item = _normalize_for_match(line)
            if (
                norm_item not in _CASUAL_EXACT
                and not _CASUAL_PATTERN.match(line)
                and not _EDITING_IMPERATIVE_PATTERN.match(line)
            ):
                kept_lines.append(line)

    if not kept_lines:
        return None

    assembled = "\n".join(kept_lines).strip()
    if (
        not had_citable_sentence
        and not classify_user_message(assembled, retriever=retriever).citable
    ):
        return None
    if len(_word_tokens(assembled)) < 4 and _count_factual_signals(assembled) == 0:
        return None
    return assembled


__all__ = [
    "ClassifierLayer",
    "SourceCategory",
    "SourceClassification",
    "classify_user_message",
    "extract_citable_source_text",
]
