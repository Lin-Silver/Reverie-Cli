"""
Web Search Tool - integrated search and content fetching.

Enhancement highlights:
- provider fallback (DDG -> Brave)
- retry/backoff for transient HTTP failures
- bounded concurrent fetch pipeline
- result normalization, dedupe, and domain filters
"""

from typing import Optional, Dict, List, Any
import concurrent.futures
import copy
import json
import logging
import random
import re
import threading
import time
import warnings
from collections import OrderedDict
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

from .base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    name = "web_search"

    description = """Search the web and optionally fetch readable page content."""

    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query text."},
            "max_results": {"type": "integer", "description": "Max results (default: 5).", "default": 5},
            "fetch_content": {"type": "boolean", "description": "Fetch page content (default: true).", "default": True},
            "include_domains": {"type": "array", "items": {"type": "string"}},
            "exclude_domains": {"type": "array", "items": {"type": "string"}},
            "recency": {"type": "string", "description": "DDG recency hint: d/w/m/y."},
            "request_timeout": {"type": "integer", "default": 15},
            "max_retries": {"type": "integer", "default": 2},
            "fetch_workers": {"type": "integer", "default": 4},
            "max_content_chars": {"type": "integer", "default": 7000},
            "output_format": {"type": "string", "enum": ["text", "markdown"], "default": "text"},
        },
        "required": ["query"],
    }

    DEFAULT_MAX_RESULTS = 5
    MAX_ALLOWED_RESULTS = 12
    DEFAULT_TIMEOUT = 15
    DEFAULT_MAX_RETRIES = 2
    DEFAULT_FETCH_WORKERS = 4
    MAX_FETCH_WORKERS = 8
    DEFAULT_MAX_CONTENT_CHARS = 7000
    MAX_CONTENT_CHARS_LIMIT = 25000
    RETRY_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504, 522, 524}
    ALLOWED_RECENCY = {"d", "w", "m", "y"}
    CACHE_SIZE = 128
    USER_AGENTS = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    )

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._ddg_backend: Optional[str] = None
        self._thread_local = threading.local()
        self._cache_lock = threading.Lock()
        self._search_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._check_deps()
        self._setup_logging()

    def _setup_logging(self) -> None:
        self.logger = logging.getLogger("reverie.tools.web_search")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            self.logger.addHandler(logging.NullHandler())
        self.logger.propagate = False

    def _check_deps(self) -> None:
        self._available = True
        self._ddg_backend = None
        try:
            import requests  # noqa: F401
            import bs4  # noqa: F401
        except ImportError:
            self._available = False
            return
        try:
            from ddgs import DDGS  # noqa: F401
            self._ddg_backend = "ddgs"
            return
        except Exception:
            pass
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r".*duckduckgo_search.*renamed to `ddgs`.*",
                    category=RuntimeWarning,
                )
                from duckduckgo_search import DDGS  # noqa: F401
            self._ddg_backend = "duckduckgo_search"
        except Exception:
            self._ddg_backend = None

    def _get_http_session(self):
        import requests
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    @staticmethod
    def _coerce_int(value: Any, default: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(min_value, min(parsed, max_value))

    @staticmethod
    def _coerce_bool(value: Any, default: bool = True) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() not in {"0", "false", "no", "off"}

    @staticmethod
    def _normalize_domain_list(value: Any) -> List[str]:
        if value is None:
            return []
        items = [value] if isinstance(value, str) else (value if isinstance(value, list) else [])
        normalized: List[str] = []
        for item in items:
            raw = str(item or "").strip().lower()
            if not raw:
                continue
            if "://" not in raw:
                raw = f"http://{raw}"
            host = (urlparse(raw).hostname or "").strip(".").lower()
            if host and host not in normalized:
                normalized.append(host)
        return normalized

    @staticmethod
    def _domain_matches(host: str, rule: str) -> bool:
        return host == rule or host.endswith(f".{rule}")

    def _passes_domain_filters(self, url: str, include_domains: List[str], exclude_domains: List[str]) -> bool:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        if include_domains and not any(self._domain_matches(host, rule) for rule in include_domains):
            return False
        if exclude_domains and any(self._domain_matches(host, rule) for rule in exclude_domains):
            return False
        return True

    @staticmethod
    def _normalize_url(url: str) -> str:
        raw = str(url or "").strip()
        if not raw:
            return ""
        parsed = urlsplit(raw)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ""
        normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))
        if normalized.endswith("/") and parsed.path and parsed.path != "/":
            normalized = normalized[:-1]
        return normalized

    @staticmethod
    def _clean_text(text: str, keep_newlines: bool = False) -> str:
        if not text:
            return ""
        text = text.replace("\x00", " ")
        if keep_newlines:
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            text = re.sub(r"[ \t\f\v]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        return text if len(text) <= max_chars else f"{text[:max_chars].rstrip()} ...[truncated]"

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._cache_lock:
            value = self._search_cache.get(key)
            if value is None:
                return None
            self._search_cache.move_to_end(key)
            return copy.deepcopy(value)

    def _cache_put(self, key: str, value: Dict[str, Any]) -> None:
        with self._cache_lock:
            self._search_cache[key] = copy.deepcopy(value)
            self._search_cache.move_to_end(key)
            while len(self._search_cache) > self.CACHE_SIZE:
                self._search_cache.popitem(last=False)

    @staticmethod
    def _compute_backoff(attempt: int, retry_after: Optional[str] = None) -> float:
        retry_after_value = None
        if retry_after:
            try:
                retry_after_value = float(retry_after)
            except (TypeError, ValueError):
                retry_after_value = None
        base = 0.75 * (2 ** attempt) + random.uniform(0.0, 0.35)
        if retry_after_value and retry_after_value > 0:
            base = max(base, retry_after_value)
        return min(base, 10.0)

    def _request_with_retry(self, url: str, *, params: Optional[Dict[str, Any]], timeout: int, max_retries: int):
        import requests
        last_response = None
        for attempt in range(max_retries + 1):
            try:
                session = self._get_http_session()
                response = session.get(
                    url,
                    params=params,
                    timeout=timeout,
                    allow_redirects=True,
                    headers={"User-Agent": random.choice(self.USER_AGENTS)},
                )
                last_response = response
                if response.status_code in self.RETRY_HTTP_CODES and attempt < max_retries:
                    time.sleep(self._compute_backoff(attempt, response.headers.get("Retry-After")))
                    continue
                return response
            except requests.RequestException:
                if attempt < max_retries:
                    time.sleep(self._compute_backoff(attempt))
                    continue
                raise
        return last_response

    def _normalize_search_results(
        self,
        raw_results: List[Dict[str, Any]],
        max_results: int,
        include_domains: List[str],
        exclude_domains: List[str],
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        seen = set()
        for idx, item in enumerate(raw_results or []):
            if not isinstance(item, dict):
                continue
            href = self._normalize_url(str(item.get("href") or item.get("url") or item.get("link") or ""))
            if not href or href in seen:
                continue
            if not self._passes_domain_filters(href, include_domains, exclude_domains):
                continue
            seen.add(href)
            title = self._clean_text(str(item.get("title") or item.get("name") or href))
            snippet = self._clean_text(str(item.get("body") or item.get("snippet") or item.get("description") or ""))
            normalized.append({"title": title or href, "href": href, "body": self._truncate_text(snippet, 360), "rank": idx + 1})
            if len(normalized) >= max_results:
                break
        return normalized

    def _search_ddg(
        self,
        query: str,
        max_results: int,
        recency: str,
        include_domains: List[str],
        exclude_domains: List[str],
    ) -> List[Dict[str, Any]]:
        if not self._ddg_backend:
            return []
        try:
            if self._ddg_backend == "ddgs":
                from ddgs import DDGS
            else:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message=r".*duckduckgo_search.*renamed to `ddgs`.*", category=RuntimeWarning)
                    from duckduckgo_search import DDGS
            kwargs: Dict[str, Any] = {"max_results": max(max_results * 2, max_results)}
            if recency in self.ALLOWED_RECENCY:
                kwargs["timelimit"] = recency
            with DDGS() as ddgs:
                try:
                    raw_results = list(ddgs.text(query, **kwargs) or [])
                except TypeError:
                    kwargs.pop("timelimit", None)
                    raw_results = list(ddgs.text(query, **kwargs) or [])
            return self._normalize_search_results(raw_results, max_results, include_domains, exclude_domains)
        except Exception as e:
            self.logger.debug(f"DDG search failed: {e}")
            return []

    def _search_brave(
        self,
        query: str,
        max_results: int,
        timeout: int,
        max_retries: int,
        include_domains: List[str],
        exclude_domains: List[str],
    ) -> List[Dict[str, Any]]:
        from bs4 import BeautifulSoup
        try:
            response = self._request_with_retry(
                "https://search.brave.com/search",
                params={"q": query, "source": "web"},
                timeout=timeout,
                max_retries=max_retries,
            )
            if response is None or response.status_code != 200:
                return []
            soup = BeautifulSoup(response.text, "html.parser")
            raw_results: List[Dict[str, str]] = []
            for block in soup.select("div.snippet, div[class*='snippet'], div[data-testid='result']"):
                if len(raw_results) >= max_results * 2:
                    break
                link = block.select_one("a[href]")
                if not link:
                    continue
                raw_results.append(
                    {
                        "title": self._clean_text(link.get_text(" ", strip=True)),
                        "href": str(link.get("href") or ""),
                        "body": self._clean_text(block.get_text(" ", strip=True)),
                    }
                )
            if not raw_results:
                for link in soup.select("a[href]"):
                    if len(raw_results) >= max_results * 2:
                        break
                    title = self._clean_text(link.get_text(" ", strip=True))
                    href = str(link.get("href") or "")
                    if title and href:
                        raw_results.append({"title": title, "href": href, "body": ""})
            return self._normalize_search_results(raw_results, max_results, include_domains, exclude_domains)
        except Exception as e:
            self.logger.debug(f"Brave search failed: {e}")
            return []

    @staticmethod
    def _extract_metadata(soup) -> Dict[str, str]:
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        desc = ""
        desc_node = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if desc_node:
            desc = str(desc_node.get("content") or "").strip()
        return {"title": title, "description": desc}

    def _select_main_node(self, soup):
        best_node = None
        best_score = -1
        selectors = ["article", "main", "[role='main']", ".content", ".post-content", ".entry-content", "#content", "#main", ".main", ".markdown-body"]
        for selector in selectors:
            for node in soup.select(selector):
                text = node.get_text(" ", strip=True)
                text_len = len(text)
                if text_len < 120:
                    continue
                link_len = sum(len(a.get_text(" ", strip=True)) for a in node.find_all("a"))
                score = text_len - int(link_len * 1.2)
                if score > best_score:
                    best_score = score
                    best_node = node
        return best_node or soup.body

    def _extract_links(self, node, base_url: str, limit: int = 8) -> List[str]:
        links: List[str] = []
        seen = set()
        if node is None:
            return links
        for a in node.find_all("a", href=True):
            href = self._normalize_url(urljoin(base_url, str(a.get("href") or "").strip()))
            if not href or href in seen:
                continue
            seen.add(href)
            links.append(href)
            if len(links) >= limit:
                break
        return links

    def _fetch_page_payload(
        self,
        url: str,
        timeout: int,
        max_retries: int,
        max_content_chars: int,
        output_format: str,
    ) -> Dict[str, Any]:
        from bs4 import BeautifulSoup

        normalized_url = self._normalize_url(url)
        if not normalized_url:
            return {"fetch_status": "error", "fetched_content": "[Error: Invalid URL]", "fetched_title": "", "fetched_description": "", "outbound_links": []}
        try:
            response = self._request_with_retry(normalized_url, params=None, timeout=timeout, max_retries=max_retries)
        except Exception as e:
            return {"fetch_status": "error", "fetched_content": f"[Error: {str(e)}]", "fetched_title": "", "fetched_description": "", "outbound_links": []}
        if response is None or response.status_code >= 400:
            status = response.status_code if response is not None else "N/A"
            return {"fetch_status": "error", "fetched_content": f"[Error: HTTP {status}]", "fetched_title": "", "fetched_description": "", "outbound_links": []}
        soup = BeautifulSoup(response.content, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe", "img", "video", "audio", "svg", "nav", "header", "footer", "form", "aside", "button", "canvas"]):
            tag.decompose()
        metadata = self._extract_metadata(soup)
        main = self._select_main_node(soup)
        if main is None:
            return {"fetch_status": "error", "fetched_content": "[No readable text found]", "fetched_title": metadata["title"], "fetched_description": metadata["description"], "outbound_links": []}
        if output_format == "markdown":
            content = self._clean_text(main.get_text("\n", strip=True), keep_newlines=True)
        else:
            content = self._clean_text(main.get_text(" ", strip=True), keep_newlines=False)
        if not content:
            content = "[No readable text found]"
        return {
            "fetch_status": "ok",
            "fetched_content": self._truncate_text(content, max_content_chars),
            "fetched_title": self._clean_text(metadata["title"]),
            "fetched_description": self._truncate_text(self._clean_text(metadata["description"]), 500),
            "outbound_links": self._extract_links(main, normalized_url),
        }

    def get_execution_message(self, **kwargs) -> str:
        query = str(kwargs.get("query") or "").strip()
        max_results = kwargs.get("max_results", self.DEFAULT_MAX_RESULTS)
        if query:
            if len(query) > 72:
                query = f"{query[:69]}..."
            return f"Executing web_search: {query} (max_results={max_results})"
        return "Executing web_search..."

    def execute(self, **kwargs) -> ToolResult:
        if not self._available:
            return ToolResult.fail("Missing dependencies. Install: pip install requests beautifulsoup4 ddgs")

        query = str(kwargs.get("query") or "").strip()
        if not query:
            return ToolResult.fail("Query is required")

        max_results = self._coerce_int(kwargs.get("max_results", self.DEFAULT_MAX_RESULTS), self.DEFAULT_MAX_RESULTS, 1, self.MAX_ALLOWED_RESULTS)
        fetch_content = self._coerce_bool(kwargs.get("fetch_content"), True)
        include_domains = self._normalize_domain_list(kwargs.get("include_domains"))
        exclude_domains = self._normalize_domain_list(kwargs.get("exclude_domains"))
        recency = str(kwargs.get("recency") or "").strip().lower()
        if recency not in self.ALLOWED_RECENCY:
            recency = ""
        request_timeout = self._coerce_int(kwargs.get("request_timeout", self.DEFAULT_TIMEOUT), self.DEFAULT_TIMEOUT, 5, 90)
        max_retries = self._coerce_int(kwargs.get("max_retries", self.DEFAULT_MAX_RETRIES), self.DEFAULT_MAX_RETRIES, 0, 6)
        fetch_workers = self._coerce_int(kwargs.get("fetch_workers", self.DEFAULT_FETCH_WORKERS), self.DEFAULT_FETCH_WORKERS, 1, self.MAX_FETCH_WORKERS)
        max_content_chars = self._coerce_int(kwargs.get("max_content_chars", self.DEFAULT_MAX_CONTENT_CHARS), self.DEFAULT_MAX_CONTENT_CHARS, 1000, self.MAX_CONTENT_CHARS_LIMIT)
        output_format = str(kwargs.get("output_format") or "text").strip().lower()
        if output_format not in {"text", "markdown"}:
            output_format = "text"

        cache_key = json.dumps({"query": query, "max_results": max_results, "recency": recency, "include": include_domains, "exclude": exclude_domains}, sort_keys=True, ensure_ascii=False)
        cached = self._cache_get(cache_key)
        if cached is None:
            attempts: List[Dict[str, Any]] = []
            results = self._search_ddg(query, max_results, recency, include_domains, exclude_domains)
            attempts.append({"provider": "ddg", "count": len(results)})
            engine = "ddg" if results else "none"
            if not results:
                results = self._search_brave(query, max_results, request_timeout, max_retries, include_domains, exclude_domains)
                attempts.append({"provider": "brave", "count": len(results)})
                engine = "brave" if results else "none"
            cached = {"results": results, "engine": engine, "attempts": attempts}
            self._cache_put(cache_key, cached)
            search_cached = False
        else:
            search_cached = True

        results = cached.get("results", [])
        engine = cached.get("engine", "none")
        attempts = cached.get("attempts", [])

        if not results:
            return ToolResult.ok(
                f"No results found for: {query} (checked DDG and Brave)",
                data={"count": 0, "results": [], "engine": "none", "attempts": attempts, "cached": search_cached},
            )

        if fetch_content:
            workers = min(fetch_workers, len(results))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_index = {
                    executor.submit(self._fetch_page_payload, res["href"], request_timeout, max_retries, max_content_chars, output_format): i
                    for i, res in enumerate(results)
                }
                for future in concurrent.futures.as_completed(future_to_index):
                    idx = future_to_index[future]
                    try:
                        payload = future.result()
                    except Exception as exc:
                        payload = {"fetch_status": "error", "fetched_content": f"[Error fetching content: {str(exc)}]", "fetched_title": "", "fetched_description": "", "outbound_links": []}
                    results[idx].update(payload)

        summary = ", ".join(f"{a['provider']}:{a['count']}" for a in attempts) if attempts else "none"
        output_parts = [f"# Search Results for: {query}", f"**Engine:** {engine}", f"**Provider Attempts:** {summary}", f"**Search Cache:** {'hit' if search_cached else 'miss'}", ""]
        for i, res in enumerate(results, 1):
            output_parts.append(f"## {i}. {res.get('title', 'No Title')}")
            output_parts.append(f"**Source:** {res.get('href', '#')}")
            output_parts.append(f"**Snippet:** {res.get('body', '')}")
            if fetch_content:
                output_parts.append(f"**Fetch Status:** {res.get('fetch_status', 'n/a')}")
                if res.get("fetched_title"):
                    output_parts.append(f"**Page Title:** {res.get('fetched_title')}")
                if res.get("fetched_description"):
                    output_parts.append(f"**Page Description:** {res.get('fetched_description')}")
                links = res.get("outbound_links") or []
                if links:
                    output_parts.append("**Outbound Links (sample):**")
                    for link in links[:6]:
                        output_parts.append(f"- {link}")
                content = str(res.get("fetched_content") or "")
                if content:
                    output_parts.append("")
                    output_parts.append("**Extracted Content:**")
                    output_parts.append(f"```{'markdown' if output_format == 'markdown' else 'text'}")
                    output_parts.append(content.replace("```", "'''"))
                    output_parts.append("```")
            output_parts.append("---")

        return ToolResult.ok(
            "\n".join(output_parts),
            data={
                "count": len(results),
                "results": results,
                "engine": engine,
                "attempts": attempts,
                "cached": search_cached,
                "settings": {
                    "fetch_content": fetch_content,
                    "fetch_workers": fetch_workers,
                    "request_timeout": request_timeout,
                    "max_retries": max_retries,
                    "max_content_chars": max_content_chars,
                    "output_format": output_format,
                    "include_domains": include_domains,
                    "exclude_domains": exclude_domains,
                    "recency": recency,
                },
            },
        )
