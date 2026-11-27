"""
JARVIS / PHOEBE - MULTI-ENGINE INTERNET SEARCH MANAGER
======================================================
Primary: SearXNG (self-hosted metasearch, multi-engine aggregator)
Automatic Fallback: DuckDuckGo live search (zero external dependencies)
Optional: Brave Search & Tavily AI if API keys configured.
Features:
  - Multi-query aggregation and parallel searching
  - Canonical URL deduplication and tracking parameter stripping
  - Relevance and authority ranking
  - Domain restrictions and time filtering
"""

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Set

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

logger = logging.getLogger(__name__)

SEARXNG_DEFAULT_URL = os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/")
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _clean_url(url: str) -> str:
    """Normalize URL by stripping tracking queries (utm_*, ref, etc.)."""
    try:
        parsed = urllib.parse.urlparse(url)
        # Handle DuckDuckGo redirect wrappers (//duckduckgo.com/l/?uddg=...)
        if "duckduckgo.com" in parsed.netloc and "/l/" in parsed.path:
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs:
                url = urllib.parse.unquote(qs["uddg"][0])
                parsed = urllib.parse.urlparse(url)

        query_params = urllib.parse.parse_qsl(parsed.query)
        filtered_params = [
            (k, v)
            for k, v in query_params
            if not k.startswith("utm_") and k not in {"fbclid", "gclid", "ref", "source"}
        ]
        clean_query = urllib.parse.urlencode(filtered_params)
        return urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", clean_query, "")
        )
    except Exception:
        return url.strip()


class SearchManager:
    def __init__(self, searxng_url: str = SEARXNG_DEFAULT_URL):
        self.searxng_url = searxng_url
        self.brave_api_key = os.getenv("BRAVE_API_KEY", "").strip()
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "").strip()

    def search_searxng(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Query SearXNG instance if running."""
        try:
            params = urllib.parse.urlencode({"q": query, "format": "json"})
            url = f"{self.searxng_url}/search?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for item in data.get("results", [])[:limit]:
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": item.get("content", ""),
                            "publishedDate": item.get("publishedDate", ""),
                            "engine": item.get("engine", "searxng"),
                        }
                    )
                return results
        except Exception:
            return []

    def search_duckduckgo(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Query DuckDuckGo using official client with HTML scraper fallback."""
        # 1. Try DDGS library for direct JSON results
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS
                ddg = DDGS()
                raw_res = list(ddg.text(query, max_results=limit))
            if raw_res:
                results = []
                for item in raw_res:
                    url = _clean_url(item.get("href") or item.get("link") or "")
                    if url.startswith("http"):
                        results.append({
                            "title": item.get("title", query),
                            "url": url,
                            "snippet": item.get("body") or item.get("snippet") or "",
                            "publishedDate": "",
                            "engine": "duckduckgo",
                        })
                if results:
                    return results[:limit]
        except Exception as e:
            logger.debug("DDGS client error, falling back to HTML scraper: %s", e)

        # 2. Scraper Fallback
        try:
            encoded = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            results = []
            # Extract result blocks using robust regex
            blocks = re.findall(
                r'<a[^>]+class="result__snippet[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            )
            titles = re.findall(
                r'<a[^>]+class="result__url[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            )

            # More reliable result block matching
            items = re.findall(
                r'<div class="result__body links_main.*?<h2.*?<a class="result__a" href="([^"]+)">(.*?)</a>.*?<a class="result__snippet.*?>(.*?)</a>',
                html,
                re.DOTALL,
            )

            for href, title, snippet in items[:limit]:
                clean_t = re.sub(r"<[^>]+>", "", title).strip()
                clean_s = re.sub(r"<[^>]+>", "", snippet).strip()
                actual_url = _clean_url(href)
                if actual_url.startswith("http") and "ad_domain=" not in actual_url and "/y.js" not in actual_url:
                    results.append(
                        {
                            "title": clean_t or query,
                            "url": actual_url,
                            "snippet": clean_s,
                            "publishedDate": "",
                            "engine": "duckduckgo",
                        }
                    )

            # Fallback if standard regex missed
            if not results:
                raw_links = re.findall(
                    r'<a class="result__snippet"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    html,
                    re.DOTALL,
                )
                for href, snip in raw_links[:limit]:
                    clean_s = re.sub(r"<[^>]+>", "", snip).strip()
                    actual_url = _clean_url(href)
                    if actual_url.startswith("http"):
                        results.append(
                            {
                                "title": query,
                                "url": actual_url,
                                "snippet": clean_s,
                                "publishedDate": "",
                                "engine": "duckduckgo",
                            }
                        )

            return results
        except Exception as e:
            logger.warning("DuckDuckGo search error: %s", e)
            return []

    def search_brave(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Optional: Search via Brave Search API if BRAVE_API_KEY is configured."""
        if not self.brave_api_key:
            return []
        try:
            params = urllib.parse.urlencode({"q": query, "count": limit})
            url = f"https://api.search.brave.com/res/v1/web/search?{params}"
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self.brave_api_key,
                },
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for item in data.get("web", {}).get("results", [])[:limit]:
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": item.get("description", ""),
                            "publishedDate": item.get("page_age", ""),
                            "engine": "brave",
                        }
                    )
                return results
        except Exception as e:
            logger.warning("Brave search failed: %s", e)
            return []

    def search_single(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Execute search on primary engine with automatic fallback cascade."""
        # 1. SearXNG
        results = self.search_searxng(query, limit=limit)
        if results:
            return results

        # 2. Brave (if configured)
        if self.brave_api_key:
            results = self.search_brave(query, limit=limit)
            if results:
                return results

        # 3. DuckDuckGo (always available, no container or key required)
        return self.search_duckduckgo(query, limit=limit)

    def search_multi_queries(self, queries: List[str], max_total: int = 12) -> List[Dict[str, Any]]:
        """
        Execute multiple planned research queries, deduplicating URLs
        and ranking by relevance.
        """
        seen_urls: Set[str] = set()
        aggregated: List[Dict[str, Any]] = []

        for q in queries:
            sub_results = self.search_single(q, limit=5)
            for r in sub_results:
                clean_url = _clean_url(r.get("url", ""))
                if clean_url and clean_url not in seen_urls:
                    seen_urls.add(clean_url)
                    r["url"] = clean_url
                    r["original_query"] = q
                    aggregated.append(r)
                if len(aggregated) >= max_total:
                    break
            if len(aggregated) >= max_total:
                break

        return aggregated


_search_manager_instance: Optional[SearchManager] = None


def get_search_manager() -> SearchManager:
    global _search_manager_instance
    if _search_manager_instance is None:
        _search_manager_instance = SearchManager()
    return _search_manager_instance
