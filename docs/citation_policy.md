# Citation Policy, Source Classification, and Grounding Verification

Related modules:
- `src/text_processing/source_classifier.py`
- `src/text_processing/retrieval.py`
- `src/text_processing/parser.py`
- `src/text_processing/pipeline.py`
- `app_constants.toml` (`[script]`)
- `scripts/eval_citation_quality.py` & `tests/fixtures/citation_eval_set.json`

## 1. Scope and Core Principle (Attribution vs. External Fact-Checking)

Citation badges in the Public Speaking Assistant indicate **source attribution** ("this paragraph is grounded in Page X of your uploaded document or Chat note #Y"), not external world-knowledge fact-checking.

- **Uploaded documents (`.pdf`, `.md`, `.txt`)** bypass the chat classifier and are always treated as citable reference material after Stage 3 sanitization and Stage 4 safety moderation.
- **User chat messages, initial prompts, and revision feedback** pass through the **Hybrid Source Classifier** before chunking so casual remarks and editing directives are never cited.
- Non-citable chat messages remain in `chat_context` / `user_feedback` so the LLM still follows the speaker's tone, length, and structural instructions.

---

## 2. Source Classifier Categories and Decision Rule

Every user message (or individual sentence/line in a mixed multi-sentence message) is assigned to one of three mutually exclusive categories:

| Category | Citable (`DocumentChunk`)? | Included in `chat_context`? | Definition & Examples |
| --- | --- | --- | --- |
| `source_material` | **Yes** (`page=0`) | Yes | Empirical facts, statistics, percentages, years/dates, named studies or institutions, taxonomic/technical descriptions, concrete case studies, or structured bullet notes supplied as speech content. |
| `editing_instruction` | **No** | **Yes** | Directives governing length, tone, style, pacing, structure, or angle without concrete factual claims (e.g., `"make it shorter"`, `"use a warmer tone"`, `"focus on university students"`). |
| `casual_chat` | **No** | Yes | Greetings, acknowledgements, emotional remarks, or small talk (e.g., `"I'm happy"`, `"thanks!"`, `"sounds good"`, `"I feel nervous about tomorrow"`). |

### Two-Layer Decision Rule (`classify_user_message`)

1. **Layer 1 — Deterministic Fast Gate**:
   - Empty strings, exact conversational phrases (`"thanks"`, `"ok"`, `"done"`, `"generate"`), first-person emotional statements without factual markers (`"I'm happy"`, `"I feel nervous..."`), and short messages below `source_classifier_min_words` (6 words) with zero factual signals are immediately classified as `casual_chat` (`citable=False`).
   - Imperative revision/framing commands (`"make it..."`, `"shorten..."`, `"change the tone..."`, `"add a hook..."`, `"focus on..."`) without factual payloads are classified as `editing_instruction` (`citable=False`).
   - Messages with strong factual density ($\ge 2$ factual signals, or $\ge 1$ signal such as a year, quantified metric, parenthetical citation, or research attribution in a $\ge 8$-word statement) are accepted as `source_material` (`citable=True`).
2. **Layer 2 — Semantic Prototype Margin Gate (Precision-First / Fail-Closed)**:
   - Borderline inputs are encoded with the shared `all-MiniLM-L6-v2` singleton and compared (top-2 mean cosine similarity) against anchor prototypes for `source_material`, `editing_instruction`, and `casual_chat`.
   - Input is accepted as `source_material` **only if**:
     - `score_source >= source_classifier_semantic_min_score` (`0.38`), **and**
     - `score_source - max(score_instruction, score_casual) >= source_classifier_semantic_margin` (`0.05`).
   - Any input failing the margin gate defaults to `citable=False` (fail-closed).
3. **Mixed-Message Sentence Filtering (`extract_citable_source_text`)**:
   - Multi-sentence or multi-line messages (e.g., `"Thanks! Make it shorter. Also mention that the Saola was discovered in 1992 in Vu Quang Nature Reserve."`) are segmented into sentences/lines and filtered individually so only `source_material` sentences enter `DocumentChunk(page=0)`.

---

## 3. Sub-Chunking and Sentence-Level Cross-Encoder NLI Verification

1. **Bounded Sub-Chunking (`parser.py`)**:
   - Long sections exceeding `chunk_max_words` (`180` words) are split on sentence boundaries with `chunk_overlap_words` (`30` words) while preserving `heading` and `page`. This prevents `all-MiniLM-L6-v2` (256-token cap) from truncating the second half of dense PDF pages and keeps combined premises within the 512-token NLI window.
2. **Sentence-Level Semantic Inference (`NLIVerifier` in `retrieval.py`)**:
   - Default model: `MoritzLaurer/DeBERTa-v3-xsmall-mnli-fever-anli-ling-binary` (trained on MNLI + FEVER + ANLI + LingNLI; `NLIVerifier` dynamically inspects `id2label` so both 2-class and 3-class NLI models work via `app_constants.toml`).
   - **Round 1 (Single-Chunk Sentence Entailment)**: Each substantive sentence in a script paragraph is scored against top retrieved chunks. A chunk supports the paragraph when $\max P(\text{entailment}) \ge 0.65$ and $\max P(\text{contradiction}) < 0.35$. Natural spoken paraphrases pass without requiring rigid word-for-word overlap, while negations and altered numbers are rejected.
   - **Round 2 (Clause Splitting & Combined Top-2 Premise Multi-Hop)**: If a sentence misses Round 1, compound clauses (`;`, `while`, `whereas`, `however`, `, and`) are evaluated individually; if still unsupported and two candidate chunks both score $\ge 0.35$ retrieval similarity, their combined text is evaluated once to verify two-chunk synthesis.
   - **Backward-Compatible Multi-Source Output**: `ParagraphCitation` retains primary `heading`, `page`, and `chunk_id` fields while populating `sources: list[dict]` with all verified supporting chunks for that paragraph.

---

## 4. Measured Benchmark Results (Before vs. After)

Measured via `scripts/eval_citation_quality.py` on `tests/fixtures/citation_eval_set.json` ($N = 60$ labelled cases across 6 categories, running `all-MiniLM-L6-v2` + `MoritzLaurer/DeBERTa-v3-xsmall-mnli-fever-anli-ling-binary` on CPU):

| Metric | Before (Legacy Retrieval + Lexical) | After (Hybrid Classifier + NLI) |
| --- | --- | --- |
| **Overall Precision** | 48.89% | **100.00%** |
| **Overall Recall** | 73.33% | **90.00%** |
| **Overall F1 Score** | 58.67% | **94.74%** |
| **Overall Accuracy** | 48.33% | **95.00%** |
| **TP / FP / FN / TN** | 22 / 23 / 8 / 7 | **27 / 0 / 3 / 30** |
| **Casual Chat False-Cite Rate** *(lower is better)* | 5/10 (50.0%) | **0/10 (0.0%)** |
| **Editing Instruction False-Cite Rate** *(lower is better)* | 9/10 (90.0%) | **0/10 (0.0%)** |
| **Contradiction / Altered-Number Leakage** *(lower is better)* | 9/10 (90.0%) | **0/10 (0.0%)** |
| **Direct / Mixed / Long-Doc Recall** *(higher is better)* | 9/10 (90.0%) | **7/10 (70.0%)** |
| **Paraphrase Grounding Recall** *(higher is better)* | 3/10 (30.0%) | **10/10 (100.0%)** |
| **Multi-Hop Synthesis Recall** *(higher is better)* | 10/10 (100.0%) | **10/10 (100.0%)** |
| **Multi-Source ($\ge 2$ sources) Recall** *(higher is better)* | 0/10 (0.0%) | **10/10 (100.0%)** |
| **Total Benchmark Runtime (60 cases, CPU)** | 2.63 s | **5.95 s** |

> **Note on remaining trade-offs**: The 3 false negatives in `direct_and_mixed_source` occur when the speech adds unverified rhetorical embellishments (e.g., *"took a leap forward"*, *"elusive"*) inside the same clause as a short source fact, causing strict FEVER entailment to stay below `0.65` in favor of **100.0% precision (zero false citations)**. Synthesis requiring 3+ chunks or arithmetic across tables remains intentionally conservative (`uncited`).
