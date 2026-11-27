"""
NexonAI Phase 7 Test Suite — Vision Module, Document Reader & Safe File Ops
===========================================================================
Comprehensive unittest suite covering:
1. vision_enabled()
2. analyze_image()
3. take_permissioned_screenshot()
4. _check_path_allowed()
5. tool_file_search()
6. tool_read_document()
7. tool_summarize_document()
8. tool_create_file()
9. tool_delete_file()
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.tools.file_search import (
    _ROOT,
    _check_path_allowed,
    tool_create_file,
    tool_delete_file,
    tool_file_search,
    tool_read_document,
    tool_summarize_document,
)
from backend.vision import analyze_image, take_permissioned_screenshot, vision_enabled


class TestVisionModule(unittest.TestCase):
    def test_vision_enabled_model_present(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "qwen3.5:4b"}, {"name": "qwen3-vl:4b"}]
        }
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            self.assertTrue(vision_enabled())
            mock_get.assert_called_once()

    def test_vision_enabled_model_absent(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "qwen3.5:4b"}]}
        with patch("httpx.get", return_value=mock_resp):
            self.assertFalse(vision_enabled())

    def test_vision_enabled_connection_error(self):
        with patch("httpx.get", side_effect=RuntimeError("connection refused")):
            self.assertFalse(vision_enabled())

    def test_analyze_image_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "sample.png"
            img_path.write_bytes(b"\x89PNG\r\n\x1a\nfake_png_bytes")

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "message": {"content": "A sample test image."}
            }

            with patch("httpx.post", return_value=mock_resp) as mock_post:
                res = analyze_image(str(img_path), prompt="What is this?")
                self.assertTrue(res["ok"])
                self.assertEqual(res["image"], "sample.png")
                self.assertEqual(res["analysis"], "A sample test image.")
                mock_post.assert_called_once()
                call_kwargs = mock_post.call_args.kwargs
                self.assertEqual(call_kwargs["json"]["model"], "qwen3-vl:4b")

    def test_analyze_image_file_not_found(self):
        res = analyze_image("nonexistent_image_xyz_123.png")
        self.assertFalse(res["ok"])
        self.assertIn("not found", res["error"].lower())

    def test_analyze_image_unsupported_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = Path(tmpdir) / "notes.txt"
            txt_path.write_text("not an image", encoding="utf-8")
            res = analyze_image(str(txt_path))
            self.assertFalse(res["ok"])
            self.assertIn("unsupported", res["error"].lower())

    def test_analyze_image_ollama_http_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "sample.jpg"
            img_path.write_bytes(b"fake_jpg")
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            with patch("httpx.post", return_value=mock_resp):
                res = analyze_image(str(img_path))
                self.assertFalse(res["ok"])
                self.assertIn("500", res["error"])

    def test_take_permissioned_screenshot_success(self):
        mock_guard = MagicMock()
        with patch("backend.automation.guard.get_automation_guard", return_value=mock_guard), \
             patch("backend.automation.system_control.take_screenshot", return_value=(True, r"Screenshot saved: C:\Users\test\shot.png")):
            res = take_permissioned_screenshot()
            self.assertTrue(res["ok"])
            self.assertEqual(res["path"], r"C:\Users\test\shot.png")
            mock_guard.log_action.assert_called_once()
            self.assertEqual(mock_guard.log_action.call_args.kwargs["action"], "screenshot")

    def test_take_permissioned_screenshot_failure(self):
        mock_guard = MagicMock()
        with patch("backend.automation.guard.get_automation_guard", return_value=mock_guard), \
             patch("backend.automation.system_control.take_screenshot", return_value=(False, "Display unavailable")):
            res = take_permissioned_screenshot()
            self.assertFalse(res["ok"])
            self.assertEqual(res["error"], "Display unavailable")
            mock_guard.log_action.assert_called_once()


class TestPathAllowlistAndFileSearch(unittest.TestCase):
    def test_check_path_allowed_valid_paths(self):
        self.assertTrue(_check_path_allowed(Path.home() / "Documents" / "test.txt"))
        self.assertTrue(_check_path_allowed(_ROOT / "backend" / "tools" / "file_search.py"))
        self.assertTrue(_check_path_allowed("backend/tools/file_search.py"))

    def test_check_path_allowed_blocked_paths(self):
        self.assertFalse(_check_path_allowed(r"C:\Windows\System32\cmd.exe"))
        self.assertFalse(_check_path_allowed(r"C:\Windows"))
        self.assertFalse(_check_path_allowed(r"Z:\OutsideAllowlist\secret.txt"))
        self.assertFalse(_check_path_allowed(Path.home() / ".." / ".." / "Windows"))

    def test_file_search_normal_and_skip_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "report.txt").write_text("hello", encoding="utf-8")
            (base / "sub").mkdir()
            (base / "sub" / "notes.txt").write_text("world", encoding="utf-8")
            for skip in (".git", "node_modules", "__pycache__", ".venv"):
                d = base / skip
                d.mkdir()
                (d / "ignored.txt").write_text("skip", encoding="utf-8")

            matches = tool_file_search("*.txt", directory=str(base), max_results=20)
            basenames = {Path(m).name for m in matches}
            self.assertEqual(basenames, {"report.txt", "notes.txt"})
            self.assertNotIn("ignored.txt", basenames)

    def test_file_search_blocked_directory(self):
        matches = tool_file_search("*", directory=r"C:\Windows\System32")
        self.assertEqual(matches, [])


class TestDocumentReaderAndSummarizer(unittest.TestCase):
    def test_read_document_text_formats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            for ext, body in [
                (".txt", "plain text content"),
                (".md", "# Heading\nBody"),
                (".py", "print('hello')"),
                (".json", '{"key": "value"}'),
            ]:
                p = base / f"sample{ext}"
                p.write_text(body, encoding="utf-8")
                res = tool_read_document(str(p))
                self.assertTrue(res["ok"], f"Failed for {ext}: {res}")
                self.assertEqual(res["text"], body)

    def test_read_document_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "data.csv"
            lines = ["name,role"] + [f"user{i},dev" for i in range(60)]
            csv_path.write_text("\n".join(lines), encoding="utf-8")

            res = tool_read_document(str(csv_path), max_chars=10000)
            self.assertTrue(res["ok"])
            self.assertEqual(res["file"], "data.csv")
            output_lines = res["text"].splitlines()
            self.assertEqual(len(output_lines), 50)
            self.assertIn("name: user0, role: dev", output_lines[0])

    def test_read_document_pdf_mocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "doc.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")

            mock_page = MagicMock()
            mock_page.extract_text.return_value = "PDF page one content"
            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]

            mock_pypdf = MagicMock()
            mock_pypdf.PdfReader.return_value = mock_reader

            with patch.dict(sys.modules, {"pypdf": mock_pypdf}):
                res = tool_read_document(str(pdf_path))
                self.assertTrue(res["ok"])
                self.assertEqual(res["file"], "doc.pdf")
                self.assertIn("PDF page one content", res["text"])

    def test_read_document_blocked_and_missing(self):
        blocked = tool_read_document(r"C:\Windows\win.ini")
        self.assertFalse(blocked["ok"])
        self.assertIn("denied", blocked["error"].lower())

        with tempfile.TemporaryDirectory() as tmpdir:
            missing = tool_read_document(str(Path(tmpdir) / "does_not_exist.txt"))
            self.assertFalse(missing["ok"])
            self.assertIn("does not exist", missing["error"].lower())

    def test_summarize_document_ollama_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "article.txt"
            p.write_text("Long article content about local AI.", encoding="utf-8")

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"message": {"content": "Summary: Local AI."}}

            with patch("httpx.post", return_value=mock_resp) as mock_post:
                res = tool_summarize_document(str(p))
                self.assertTrue(res["ok"])
                self.assertEqual(res["summary"], "Summary: Local AI.")
                self.assertEqual(mock_post.call_args.kwargs["json"]["model"], "qwen3.5:4b")

    def test_summarize_document_ollama_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "article.txt"
            long_text = "A" * 800
            p.write_text(long_text, encoding="utf-8")

            with patch("httpx.post", side_effect=RuntimeError("Ollama down")):
                res = tool_summarize_document(str(p))
                self.assertTrue(res["ok"])
                self.assertTrue(res.get("fallback"))
                self.assertEqual(len(res["summary"]), 500)


class TestSafeFileOperations(unittest.TestCase):
    def test_create_file_new_and_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "created.txt"

            # New file succeeds immediately
            res_new = tool_create_file(str(target), "initial content", overwrite=False)
            self.assertTrue(res_new["ok"])
            self.assertEqual(target.read_text(encoding="utf-8"), "initial content")

            # Existing file with overwrite=False returns error
            res_dup = tool_create_file(str(target), "new content", overwrite=False)
            self.assertFalse(res_dup["ok"])
            self.assertIn("already exists", res_dup["error"].lower())
            self.assertEqual(target.read_text(encoding="utf-8"), "initial content")

            # Existing file with overwrite=True requires confirmation and does NOT write yet
            mock_guard = MagicMock()
            mock_guard.request_confirmation.return_value = MagicMock(
                status="pending_confirm",
                confirmation_id="abc12345",
                message="Confirmation required (abc12345)",
            )
            with patch("backend.tools.file_search.get_automation_guard", return_value=mock_guard):
                res_ow = tool_create_file(str(target), "overwritten content", overwrite=True)
                self.assertFalse(res_ow["ok"])
                self.assertTrue(res_ow["requires_confirmation"])
                self.assertEqual(res_ow["confirmation_id"], "abc12345")
                self.assertEqual(target.read_text(encoding="utf-8"), "initial content")
                mock_guard.request_confirmation.assert_called_once()
                self.assertEqual(mock_guard.request_confirmation.call_args.kwargs["action"], "overwrite_file")

    def test_create_file_blocked_path(self):
        res = tool_create_file(r"C:\Windows\Temp\evil.txt", "nope")
        self.assertFalse(res["ok"])
        self.assertIn("denied", res["error"].lower())

    def test_delete_file_requires_confirmation_and_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "to_delete.txt"
            target.write_text("keep me until confirmed", encoding="utf-8")

            mock_guard = MagicMock()
            mock_guard.request_confirmation.return_value = MagicMock(
                status="pending_confirm",
                confirmation_id="del99999",
                message="Confirmation required (del99999)",
            )
            with patch("backend.tools.file_search.get_automation_guard", return_value=mock_guard):
                res = tool_delete_file(str(target))
                self.assertFalse(res["ok"])
                self.assertTrue(res["requires_confirmation"])
                self.assertEqual(res["confirmation_id"], "del99999")
                self.assertTrue(target.exists())
                mock_guard.request_confirmation.assert_called_once()
                self.assertEqual(mock_guard.request_confirmation.call_args.kwargs["action"], "delete_file")

        blocked = tool_delete_file(r"C:\Windows\System32\drivers\etc\hosts")
        self.assertFalse(blocked["ok"])
        self.assertIn("denied", blocked["error"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
