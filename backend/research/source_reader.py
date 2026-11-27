"""
JARVIS / PHOEBE - WEB SOURCE READER & CONTENT EXTRACTOR
========================================================
Extracts clean, readable content from web articles and documentation:
  - Strips ads, navigation, headers, footers, script/style tags
  - Extracts title, meta description, publication date, headings, and paragraphs
  - Caches responses in data/research_cache/ for fast re-reading
  - Selects top relevant passages within a safe token budget for local Ollama
"""

import hashlib
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = _ROOT / "data" / "research_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _url_cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{h}.json"


class SourceReader:
    def __init__(self, timeout: float = 7.0, max_chars: int = 5000):
        self.timeout = timeout
        self.max_chars = max_chars

    def fetch_url(self, url: str, use_cache: bool = True) -> Optional[str]:
        """Fetch raw HTML from URL with disk caching."""
        cache_file = _url_cache_path(url)
        if use_cache and cache_file.exists():
            try:
                cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
                return cached_data.get("html", "")
            except Exception:
                pass

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # Avoid non-HTML responses
                content_type = resp.headers.get("Content-Type", "").lower()
                if "html" not in content_type and "text" not in content_type:
                    return None
                html = resp.read().decode("utf-8", errors="ignore")

                # Save to cache
                if use_cache:
                    try:
                        cache_file.write_text(
                            json.dumps({"url": url, "fetched_at": str(datetime.now()), "html": html}),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
                return html
        except Exception as e:
            logger.warning("Failed fetching %s: %s", url, e)
            return None

    def extract_article(self, url: str, html: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract clean text, headings, publication date, and title from HTML.
        Strips boilerplate, navigation, footers, ads, and scripts.
        """
        if html is None:
            html = self.fetch_url(url)

        if not html:
            return {
                "url": url,
                "title": "",
                "date": "",
                "headings": [],
                "text": "",
                "success": False,
            }

        # 1. Extract Title
        title = ""
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = re.sub(r"\s+", " ", title_match.group(1)).strip()

        # 2. Extract Publication Date
        date_str = ""
        date_patterns = [
            r'<meta[^>]+property="article:published_time"[^>]+content="([^"]+)"',
            r'<meta[^>]+name="date"[^>]+content="([^"]+)"',
            r'<meta[^>]+name="pubdate"[^>]+content="([^"]+)"',
            r'<time[^>]*datetime="([^"]+)"',
        ]
        for dp in date_patterns:
            m = re.search(dp, html, re.IGNORECASE)
            if m:
                date_str = m.group(1).split("T")[0]
                break

        # 3. Strip non-content blocks
        cleaned = re.sub(r"<(script|style|nav|header|footer|aside|noscript|svg)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # 4. Extract Headings (h1, h2, h3)
        headings = []
        h_matches = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", cleaned, re.IGNORECASE | re.DOTALL)
        for h in h_matches:
            clean_h = re.sub(r"<[^>]+>", "", h).strip()
            if clean_h and len(clean_h) < 120:
                headings.append(clean_h)

        # 5. Extract Paragraphs and list items
        paragraphs = []
        p_matches = re.findall(r"<(?:p|li)[^>]*>(.*?)</(?:p|li)>", cleaned, re.IGNORECASE | re.DOTALL)
        for p in p_matches:
            clean_p = re.sub(r"<[^>]+>", "", p).strip()
            clean_p = re.sub(r"\s+", " ", clean_p)
            if len(clean_p) > 35:  # Skip tiny fragments
                paragraphs.append(clean_p)

        full_text = "\n\n".join(paragraphs)

        # Truncate to maximum characters to stay within local LLM context limits
        if len(full_text) > self.max_chars:
            full_text = full_text[:self.max_chars] + "\n...[truncated]"

        return {
            "url": url,
            "title": title,
            "date": date_str,
            "headings": headings[:8],
            "text": full_text,
            "success": bool(full_text),
        }

    def read_sources(self, urls: List[str], max_sources: int = 4) -> List[Dict[str, Any]]:
        """Read and extract content from a list of URLs."""
        extracted_sources = []
        for u in urls[:max_sources]:
            doc = self.extract_article(u)
            if doc.get("success"):
                extracted_sources.append(doc)
        return extracted_sources


_source_reader_instance: Optional[SourceReader] = None


def get_source_reader() -> SourceReader:
    global _source_reader_instance
    if _source_reader_instance is None:
        _source_reader_instance = SourceReader()
    return _source_reader_instance
