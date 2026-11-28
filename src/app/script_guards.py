"""Content guards of the script chat and script generation routes (contract E v2)."""

from src.text_processing.contracts import ScriptGenerationError
from src.text_processing.input_guard import GIBBERISH_MESSAGE, is_gibberish


def reject_gibberish(*texts: str, has_file: bool) -> None:
    """Raise 422 `gibberish_input` when any text is junk; an attached file lets all pass."""
    if any(is_gibberish(text, has_file=has_file) for text in texts):
        raise ScriptGenerationError("gibberish_input", GIBBERISH_MESSAGE, status_code=422)
