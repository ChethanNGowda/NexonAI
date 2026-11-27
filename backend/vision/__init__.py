"""
NexonAI — Vision Module (Phase 7)
==================================
Local image analysis via qwen3-vl:4b Ollama model.
Permissioned screenshot capture via AutomationGuard.
"""
import base64
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent


def vision_enabled() -> bool:
    """Check if the qwen3-vl:4b vision model is available in Ollama."""
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            names = [m.get("name", "").split(":")[0] for m in models]
            return "qwen3-vl" in names
    except Exception:
        pass
    return False


def analyze_image(image_path: str, prompt: str = "Describe this image in detail.") -> Dict[str, Any]:
    """Analyze an image using the qwen3-vl:4b vision model via Ollama."""
    p = Path(image_path)
    if not p.is_absolute():
        p = _ROOT / p
    if not p.exists() or not p.is_file():
        return {"ok": False, "error": f"Image file not found: {image_path}"}
    allowed_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    if p.suffix.lower() not in allowed_ext:
        return {"ok": False, "error": f"Unsupported image format: {p.suffix}"}
    try:
        image_data = base64.b64encode(p.read_bytes()).decode("utf-8")
    except Exception as e:
        return {"ok": False, "error": f"Could not read image: {e}"}
    try:
        import httpx
        payload = {
            "model": "qwen3-vl:4b",
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_data],
                }
            ],
            "stream": False,
        }
        resp = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=60.0)
        if resp.status_code == 200:
            result = resp.json()
            content = result.get("message", {}).get("content", "")
            return {"ok": True, "image": p.name, "analysis": content}
        else:
            return {"ok": False, "error": f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"Vision model request failed: {e}"}


def take_permissioned_screenshot() -> Dict[str, Any]:
    """Capture a screenshot with permission logging via AutomationGuard."""
    from backend.automation.guard import get_automation_guard
    from backend.automation.system_control import take_screenshot
    guard = get_automation_guard()
    guard.log_action(action="screenshot", target="screen", status="allowed", detail="screenshot capture via vision module")
    ok, msg = take_screenshot()
    if ok:
        # Extract path from message like "Screenshot saved: C:\path\to\file.png"
        parts = msg.split(":", 1)
        path_str = parts[-1].strip() if len(parts) > 1 else ""
        return {"ok": True, "message": msg, "path": path_str}
    return {"ok": False, "error": msg}
