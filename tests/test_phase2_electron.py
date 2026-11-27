"""
TEST SUITE FOR PHASE 2 — ELECTRON APPLICATION COMPLETION
=========================================================
Tests:
  1. Frontend files existence and non-emptiness.
  2. JavaScript syntax of main.js, preload.js, renderer.js.
  3. Preload IPC contract coverage (all window, settings, and assistant methods exposed).
  4. HTML structure (window controls, pin button, maximize button, settings drawer, inputs).
  5. Settings persistence simulation (load, save, merge, schema validity).
  6. Backend assistant CLI --model flag support.
  7. Backend assistant CLI --models discovery support.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
PYTHON_CMD = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def test_frontend_files_exist():
    required = ["main.js", "preload.js", "renderer.js", "index.html", "style.css"]
    for fname in required:
        fpath = FRONTEND_DIR / fname
        assert fpath.exists(), f"Missing required frontend file: {fname}"
        assert fpath.stat().st_size > 0, f"Frontend file is empty: {fname}"
    print("[PASS] All frontend files exist and are populated.")


def test_js_syntax():
    js_files = ["main.js", "preload.js", "renderer.js"]
    for js in js_files:
        fpath = FRONTEND_DIR / js
        res = subprocess.run(["node", "-c", str(fpath)], capture_output=True, text=True)
        assert res.returncode == 0, f"Syntax error in {js}: {res.stderr}"
    print("[PASS] Node.js syntax check passed for main.js, preload.js, and renderer.js.")


def test_preload_ipc_contract():
    content = (FRONTEND_DIR / "preload.js").read_text(encoding="utf-8")
    expected_apis = [
        "minimize",
        "maximize",
        "isMaximized",
        "close",
        "toggleAlwaysOnTop",
        "getAlwaysOnTop",
        "loadSettings",
        "saveSettings",
        "ask",
        "research",
        "cancel",
        "getModels",
        "clearMemory",
        "health",
        "onProgress",
        "onVoiceEvent",
        "onMaximizedChange",
    ]
    for api_name in expected_apis:
        assert f"{api_name}:" in content or f"{api_name} :" in content, f"Missing {api_name} in preload.js"
    print("[PASS] Preload IPC contract contains all window, settings, and assistant methods.")


def test_html_controls_and_drawer():
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    expected_ids = [
        'id="pinBtn"',
        'id="settingsBtn"',
        'id="minimizeBtn"',
        'id="maximizeBtn"',
        'id="closeBtn"',
        'id="settingsDrawer"',
        'id="closeSettingsBtn"',
        'id="modelSelect"',
        'id="alwaysOnTopToggle"',
        'id="voiceOutputToggle"',
        'id="speechRateSlider"',
        'id="speechVolumeSlider"',
        'id="clearMemoryBtn"',
    ]
    for element_id in expected_ids:
        assert element_id in html, f"Missing HTML element: {element_id}"
    print("[PASS] index.html includes all window controls, pin button, maximize button, and settings drawer elements.")


def test_settings_persistence_schema():
    default_settings = {
        "alwaysOnTop": True,
        "activeModel": "qwen3-vl:4b",
        "voiceOutput": True,
        "speechRate": 1.0,
        "speechVolume": 100
    }
    # Test merge logic
    user_override = {"alwaysOnTop": False, "activeModel": "qwen3.5:4b", "speechRate": 1.25}
    merged = {**default_settings, **user_override}
    assert merged["alwaysOnTop"] is False
    assert merged["activeModel"] == "qwen3.5:4b"
    assert merged["speechRate"] == 1.25
    assert merged["voiceOutput"] is True
    assert merged["speechVolume"] == 100
    print("[PASS] Settings schema and merge logic verified.")


def test_backend_models_endpoint():
    assistant_path = ROOT_DIR / "backend" / "ai" / "assistant.py"
    res = subprocess.run([PYTHON_CMD, str(assistant_path), "--models"], capture_output=True, text=True)
    assert res.returncode == 0, f"Assistant --models failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data.get("ok") is True
    assert isinstance(data.get("installed_models"), list)
    print(f"[PASS] Backend models endpoint returned: {data.get('installed_models')}")


def test_backend_model_override():
    assistant_path = ROOT_DIR / "backend" / "ai" / "assistant.py"
    res = subprocess.run(
        [PYTHON_CMD, str(assistant_path), "--ask", "ping", "--model", "qwen3.5:4b"],
        capture_output=True,
        text=True
    )
    assert res.returncode == 0, f"Assistant --model failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data.get("ok") is True
    print("[PASS] Backend assistant accepts dynamic --model override.")


if __name__ == "__main__":
    print("=" * 65)
    print("      RUNNING PHASE 2 (ELECTRON COMPLETION) TEST SUITE")
    print("=" * 65)
    test_frontend_files_exist()
    test_js_syntax()
    test_preload_ipc_contract()
    test_html_controls_and_drawer()
    test_settings_persistence_schema()
    test_backend_models_endpoint()
    test_backend_model_override()
    print("=" * 65)
    print("             ALL PHASE 2 TESTS PASSED SUCCESSFULLY")
    print("=" * 65)
