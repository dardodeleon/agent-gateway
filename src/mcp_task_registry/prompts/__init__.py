"""MCP Prompt definitions — loaded from Markdown files."""

from __future__ import annotations

import os
from pathlib import Path

_PROMPTS_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

def load_prompt(filename: str, **kwargs: str) -> str:
    """Load a prompt template from a .md file and format placeholders.

    Args:
        filename: Name of the .md file (without path).
        **kwargs: Placeholder values to substitute (e.g. task_description="...").

    Returns:
        The formatted prompt text.
    """
    file_path = _PROMPTS_DIR / filename
    text = file_path.read_text(encoding="utf-8")
    if kwargs:
        text = text.format(**kwargs)
    return text
