"""Stage 4 Groq LLM script generator with .env model fallback chain."""

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

from .parser import DocumentChunk

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
try:
    from groq import Groq
except ImportError:
    Groq = None


@dataclass
class ScriptResult:
    """Generated 1-minute script and verified page citations."""

    model_used: str
    script: str
    word_count: int
    citations: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScriptGenerator:
    """Generate a 1-minute English script using Groq models from .env."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "").strip()
        models = [
            os.getenv("GROQ_LLM_MODEL", "").strip() or "openai/gpt-oss-120b",
            os.getenv("GROQ_LLM_FALLBACK_MODEL_1", "").strip() or "qwen/qwen3.8-27b",
            os.getenv("GROQ_LLM_FALLBACK_MODEL_2", "").strip() or "openai/gpt-oss-20b",
        ]
        self.model_chain = list(dict.fromkeys(m for m in models if m))
        self.client = Groq(api_key=self.api_key) if (Groq and self.api_key) else None

    def verify_citations(
        self, raw_citations: list[dict[str, Any]], chunks: list[DocumentChunk]
    ) -> list[dict[str, Any]]:
        """Keep only citations pointing to real page numbers in chunks."""
        valid = {c.page for c in chunks}
        verified = [
            {"heading": str(i.get("heading", "")).strip(), "page": i["page"]}
            for i in raw_citations
            if isinstance(i, dict) and i.get("page") in valid and i.get("heading")
        ]
        return verified or [{"heading": chunks[0].heading, "page": chunks[0].page}]

    def generate_script(self, chunks: list[DocumentChunk], topic: str) -> ScriptResult:
        """Call Groq LLM in JSON mode to produce a 120-150 word English script."""
        if not self.client:
            raise RuntimeError("Missing GROQ_API_KEY in environment.")
        ctx = "\n\n".join(f"[Page {c.page} | Heading: {c.heading}]\n{c.content}" for c in chunks)
        msgs = [
            {
                "role": "system",
                "content": (
                    'Write a 120-150 word English speech script.'
                    ' Return JSON: {"script": "...",'
                    ' "citations": [{"heading": "...", "page": 1}]}'
                ),
            },
            {"role": "user", "content": f"Topic: {topic}\n\n{ctx}"},
        ]
        last_err: Exception | None = None
        for model_id in self.model_chain:
            try:
                resp = self.client.chat.completions.create(
                    model=model_id,
                    messages=msgs,
                    temperature=0.7,
                    response_format={"type": "json_object"},
                )
                data = json.loads(resp.choices[0].message.content or "{}")
                script = str(data.get("script", "")).strip()
                if not script:
                    raise ValueError("Empty script.")
                citations = self.verify_citations(data.get("citations", []), chunks)
                return ScriptResult(model_id, script, len(script.split()), citations)
            except Exception as exc:
                last_err = exc
        raise RuntimeError(f"All Groq models failed: {last_err}") from last_err
