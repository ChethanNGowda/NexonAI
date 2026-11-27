"""
JARVIS / PHOEBE - FILE SEARCH & DOCUMENT READING TOOLS
======================================================
Safe local desktop file search and multi-format document reading.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List

from backend.ai.tool_registry import global_registry

_ROOT = Path(__file__).resolve().parent.parent.parent


@global_registry.register(
    name="file_search",
    description="Search for files by filename pattern or keyword across project workspace or user folders.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Filename pattern to match (e.g. '*.py', 'report.pdf', 'notes*')."},
            "directory": {"type": "string", "description": "Directory to search in. Defaults to workspace root.", "default": ""},
            "max_results": {"type": "integer", "description": "Maximum number of file paths to return.", "default": 10},
        },
        "required": ["pattern"],
    },
)
def tool_file_search(pattern: str, directory: str = "", max_results: int = 10) -> List[str]:
    search_dir = Path(directory) if directory else _ROOT
    if not search_dir.exists():
        search_dir = _ROOT

    matches = []
    # Protect against recursive traversal of node_modules, .venv, .git
    skip_dirs = {".venv", "venv", "node_modules", ".git", "__pycache__"}

    for root, dirs, files in os.walk(search_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            from fnmatch import fnmatch
            if fnmatch(f.lower(), pattern.lower()):
                matches.append(str(Path(root) / f))
                if len(matches) >= max_results:
                    return matches
    return matches


@global_registry.register(
    name="read_document",
    description="Read and extract text from a local text, Markdown, code, JSON, or PDF file.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute or workspace-relative path to the document file."},
            "max_chars": {"type": "integer", "description": "Maximum characters to read.", "default": 4000},
        },
        "required": ["file_path"],
    },
)
def tool_read_document(file_path: str, max_chars: int = 4000) -> Dict[str, Any]:
    p = Path(file_path)
    if not p.is_absolute():
        p = _ROOT / p

    if not p.exists() or not p.is_file():
        return {"ok": False, "error": f"File '{file_path}' does not exist."}

    # Check for PDF
    if p.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(p))
            text = "\n".join([page.extract_text() or "" for page in reader.pages[:10]])
            return {"ok": True, "file": p.name, "text": text[:max_chars]}
        except Exception as e:
            return {"ok": False, "error": f"PDF reading failed: {e}"}

    # Text / code file reading
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        return {"ok": True, "file": p.name, "text": content[:max_chars]}
    except Exception as e:
        return {"ok": False, "error": f"Could not read file: {e}"}
