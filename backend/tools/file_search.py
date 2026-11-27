"""
JARVIS / PHOEBE - FILE SEARCH, DOCUMENT READING & SAFE FILE OPS
===============================================================
Safe local desktop file search, multi-format document reading/summarization,
and permission-guarded file creation/deletion.
"""

import csv
import logging
import os
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List

from backend.ai.tool_registry import global_registry
from backend.automation.guard import get_automation_guard

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWED_ROOTS = [Path.home(), _ROOT]


def _resolve_path(path_str: str) -> Path:
    """Resolve a path string relative to project root if not absolute."""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = _ROOT / p
    return p.resolve()


def _check_path_allowed(path: Any) -> bool:
    """Return True if path resolves inside ALLOWED_ROOTS (home dir or project root)."""
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = _ROOT / p
        resolved = p.resolve()
    except Exception:
        return False

    for root in ALLOWED_ROOTS:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


@global_registry.register(
    name="file_search",
    description="Search for files by filename pattern or keyword across approved project workspace or user folders.",
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
    if directory:
        search_dir = Path(directory).expanduser()
        if not search_dir.is_absolute():
            search_dir = _ROOT / search_dir
        if not _check_path_allowed(search_dir):
            logger.warning("Blocked file_search in disallowed directory: %s", directory)
            return []
        if not search_dir.exists() or not search_dir.is_dir():
            return []
    else:
        search_dir = _ROOT

    matches: List[str] = []
    # Protect against recursive traversal of node_modules, .venv, .git
    skip_dirs = {".venv", "venv", "node_modules", ".git", "__pycache__"}

    for root, dirs, files in os.walk(search_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if fnmatch(f.lower(), pattern.lower()):
                matches.append(str(Path(root) / f))
                if len(matches) >= max_results:
                    return matches
    return matches


@global_registry.register(
    name="read_document",
    description="Read and extract text from a local text, Markdown, code, JSON, CSV, or PDF file.",
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
    if not _check_path_allowed(file_path):
        return {"ok": False, "error": f"Access denied: '{file_path}' is outside approved folders."}

    p = _resolve_path(file_path)
    if not p.exists() or not p.is_file():
        return {"ok": False, "error": f"File '{file_path}' does not exist."}

    # Check for CSV
    if p.suffix.lower() == ".csv":
        try:
            with open(p, "r", encoding="utf-8", errors="ignore", newline="") as fh:
                reader = csv.DictReader(fh)
                rows: List[str] = []
                for i, row in enumerate(reader):
                    if i >= 50:
                        break
                    rows.append(", ".join(f"{k}: {v}" for k, v in row.items()))
            text = "\n".join(rows)
            return {"ok": True, "file": p.name, "text": text[:max_chars]}
        except Exception as e:
            return {"ok": False, "error": f"CSV reading failed: {e}"}

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


@global_registry.register(
    name="summarize_document",
    description="Read a local document and generate a concise summary using the local LLM.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute or workspace-relative path to the document file."},
            "max_chars": {"type": "integer", "description": "Maximum characters to read before summarizing.", "default": 4000},
        },
        "required": ["file_path"],
    },
)
def tool_summarize_document(file_path: str, max_chars: int = 4000) -> Dict[str, Any]:
    doc = tool_read_document(file_path, max_chars=max_chars)
    if not doc.get("ok"):
        return doc

    text = doc.get("text", "")
    if not text.strip():
        return {"ok": True, "file": doc.get("file", ""), "summary": ""}

    try:
        import httpx
        payload = {
            "model": "qwen3.5:4b",
            "messages": [
                {
                    "role": "user",
                    "content": f"Summarize the following document concisely:\n\n{text}",
                }
            ],
            "stream": False,
        }
        resp = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=30.0)
        if resp.status_code == 200:
            summary = resp.json().get("message", {}).get("content", "")
            if summary:
                return {"ok": True, "file": doc.get("file", ""), "summary": summary}
    except Exception as e:
        logger.warning("Ollama summarize_document fallback: %s", e)

    return {"ok": True, "file": doc.get("file", ""), "summary": text[:500], "fallback": True}


@global_registry.register(
    name="create_file",
    description="Create a new file in an approved folder. Overwriting an existing file requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute or workspace-relative path to the file to create."},
            "content": {"type": "string", "description": "Text content to write to the file."},
            "overwrite": {"type": "boolean", "description": "Whether to overwrite if file already exists (requires confirmation).", "default": False},
        },
        "required": ["file_path", "content"],
    },
)
def tool_create_file(file_path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
    if not _check_path_allowed(file_path):
        return {"ok": False, "error": f"Access denied: '{file_path}' is outside approved folders."}

    p = _resolve_path(file_path)
    if p.exists():
        if not overwrite:
            return {"ok": False, "error": "File already exists. Set overwrite=True to overwrite."}

        guard = get_automation_guard()

        def _do_overwrite() -> tuple[bool, str]:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return True, f"Overwrote {p.name}"

        decision = guard.request_confirmation(
            action="overwrite_file",
            target=str(p),
            description=f"Overwrite existing file {p.name}",
            callback=_do_overwrite,
        )
        if decision.status == "blocked":
            return {"ok": False, "error": decision.message, "blocked": True}
        return {
            "ok": False,
            "requires_confirmation": True,
            "confirmation_id": decision.confirmation_id,
            "message": decision.message,
        }

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "file": str(p), "message": f"Created {p.name}"}
    except Exception as e:
        return {"ok": False, "error": f"Could not create file: {e}"}


@global_registry.register(
    name="delete_file",
    description="Request permissioned deletion of a file in an approved folder. Always requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute or workspace-relative path to the file to delete."},
        },
        "required": ["file_path"],
    },
)
def tool_delete_file(file_path: str) -> Dict[str, Any]:
    if not _check_path_allowed(file_path):
        return {"ok": False, "error": f"Access denied: '{file_path}' is outside approved folders."}

    p = _resolve_path(file_path)
    guard = get_automation_guard()

    def _do_delete() -> tuple[bool, str]:
        if p.exists() and p.is_file():
            p.unlink()
            return True, f"Deleted {p.name}"
        return False, f"File not found: {p.name}"

    decision = guard.request_confirmation(
        action="delete_file",
        target=str(p),
        description=f"Delete file {p.name}",
        callback=_do_delete,
    )
    if decision.status == "blocked":
        return {"ok": False, "error": decision.message, "blocked": True}
    return {
        "ok": False,
        "requires_confirmation": True,
        "confirmation_id": decision.confirmation_id,
        "message": decision.message,
    }
