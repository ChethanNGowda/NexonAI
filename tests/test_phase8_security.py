"""
NexonAI Phase 8 Test Suite — Security and Error Handling
========================================================
Covers Electron IPC validation, BrowserWindow security settings,
CSP meta tag, .gitignore coverage, _safe_error_msg redaction,
hardcoded secret scanning, and path traversal rejection.
"""

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.ai.assistant import _safe_error_msg


class TestPhase8Security(unittest.TestCase):
    """Phase 8 security and error-handling verification suite."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.main_js = (ROOT_DIR / "frontend" / "main.js").read_text(encoding="utf-8")
        cls.index_html = (ROOT_DIR / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.gitignore = (ROOT_DIR / ".gitignore").read_text(encoding="utf-8")

    def test_01_ipc_validation_helpers_present(self) -> None:
        """Verify IPC sanitization and validation helpers exist and are wired in main.js."""
        for fn_name in (
            "function sanitizeString",
            "function validateModelName",
            "function validateVoiceId",
            "function validateConfirmationId",
        ):
            self.assertIn(fn_name, self.main_js, f"Missing {fn_name} in frontend/main.js")

        self.assertIn("sanitizeString(", self.main_js)
        self.assertIn("validateModelName(", self.main_js)
        self.assertIn("validateVoiceId(", self.main_js)
        self.assertIn("validateConfirmationId(", self.main_js)

    def test_02_electron_security_settings(self) -> None:
        """Verify nodeIntegration: false, contextIsolation: true, and webSecurity: true."""
        self.assertRegex(self.main_js, r"nodeIntegration\s*:\s*false")
        self.assertRegex(self.main_js, r"contextIsolation\s*:\s*true")
        self.assertRegex(self.main_js, r"webSecurity\s*:\s*true")

    def test_03_csp_meta_tag_present(self) -> None:
        """Verify Content-Security-Policy meta tag is present in frontend/index.html."""
        self.assertIn("Content-Security-Policy", self.index_html)
        self.assertRegex(
            self.index_html,
            r'<meta\s+http-equiv=["\']Content-Security-Policy["\']',
        )

    def test_04_gitignore_coverage(self) -> None:
        """Verify .gitignore covers secrets, logs, database, and dependencies."""
        lines = {line.strip() for line in self.gitignore.splitlines() if line.strip() and not line.strip().startswith("#")}
        for required in (".env", "*.env", "logs/", "data/memory.db", "node_modules/", "__pycache__/", "*.log"):
            self.assertIn(required, lines, f"Missing {required} in .gitignore")

    def test_05_safe_error_msg_redacts_secrets(self) -> None:
        """Verify _safe_error_msg redacts API keys, Bearer tokens, and env var values."""
        fake_sk = "sk-proj1234567890abcdef"
        fake_aiza = "AIzaSyD-1234567890abcdefghijklmnopqr"
        fake_bearer = "Bearer eyJhbGciOiJIUzI1NiJ9.payload"
        fake_env_secret = "super-secret-env-token-998877"

        exc_sk = RuntimeError(f"Failed with key {fake_sk}")
        self.assertNotIn(fake_sk, _safe_error_msg(exc_sk))
        self.assertIn("[REDACTED]", _safe_error_msg(exc_sk))

        exc_aiza = RuntimeError(f"Google error {fake_aiza}")
        self.assertNotIn(fake_aiza, _safe_error_msg(exc_aiza))
        self.assertIn("[REDACTED]", _safe_error_msg(exc_aiza))

        exc_bearer = RuntimeError(f"Auth header {fake_bearer}")
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", _safe_error_msg(exc_bearer))
        self.assertIn("[REDACTED]", _safe_error_msg(exc_bearer))

        with patch.dict(os.environ, {"NEXON_TEST_SECRET": fake_env_secret}):
            exc_env = RuntimeError(f"Env leak: {fake_env_secret}")
            msg = _safe_error_msg(exc_env)
            self.assertNotIn(fake_env_secret, msg)
            self.assertIn("[REDACTED]", msg)

    def test_06_no_hardcoded_secrets_in_backend(self) -> None:
        """Scan backend/**/*.py for hardcoded API keys or Bearer tokens."""
        secret_regex = re.compile(
            r"(sk-[A-Za-z0-9]{10,}|AIza[A-Za-z0-9_\-]{30,}|Bearer\s+[A-Za-z0-9._\-]{10,})"
        )
        backend_dir = ROOT_DIR / "backend"
        findings = []
        for py_file in backend_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(content.splitlines(), start=1):
                if secret_regex.search(line):
                    findings.append(f"{py_file.relative_to(ROOT_DIR)}:{lineno}")
        self.assertEqual(findings, [], f"Potential hardcoded secrets found: {findings}")

    def test_07_path_traversal_rejected_by_model_validation(self) -> None:
        """Verify the model name validation regex rejects path traversal and accepts valid models."""
        match = re.search(
            r"function\s+validateModelName\s*\([^)]*\)\s*\{[^}]*(/[^/]+/)",
            self.main_js,
        )
        self.assertIsNotNone(match, "validateModelName regex not found in frontend/main.js")
        js_regex = match.group(1).strip("/")
        py_regex = re.compile(f"^{js_regex}$" if not js_regex.startswith("^") else js_regex)

        # Reject path traversal and shell metacharacters
        for bad in ("../../../etc/passwd", "..\\..\\windows\\system32", "llama3;rm -rf /", "model\x00name"):
            self.assertIsNone(py_regex.match(bad), f"Model validator should reject {bad!r}")

        # Accept valid Ollama model names
        for good in ("qwen3-vl:4b", "qwen3.5:4b", "llama3.2:latest"):
            self.assertIsNotNone(py_regex.match(good), f"Model validator should accept {good!r}")

    def test_08_web_security_in_browser_window_options(self) -> None:
        """Verify webSecurity: true is inside BrowserWindow webPreferences in createWindow()."""
        bw_match = re.search(
            r"new\s+BrowserWindow\s*\(\{[\s\S]*?webPreferences\s*:\s*\{([\s\S]*?)\}",
            self.main_js,
        )
        self.assertIsNotNone(bw_match, "BrowserWindow webPreferences block not found")
        web_prefs = bw_match.group(1)
        self.assertRegex(web_prefs, r"webSecurity\s*:\s*true")
        self.assertRegex(web_prefs, r"nodeIntegration\s*:\s*false")
        self.assertRegex(web_prefs, r"contextIsolation\s*:\s*true")


if __name__ == "__main__":
    unittest.main(verbosity=2)
