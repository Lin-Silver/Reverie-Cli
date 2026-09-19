"""
Web Search / Web Fetch tools for external research.

Design (wigolo-inspired, keyless, deterministic):
- multi-engine search run in parallel (ddgs + Bing + Brave), not sequential
  fallback, so one engine failing barely moves the results
- Reciprocal Rank Fusion (RRF) merges the engines' rankings
- engine-consensus signal: URLs several engines agree on rank higher, and the
  per-engine success/failure is reported so degraded backends stay visible
- a deterministic evidence score (rank-fusion + query lexical overlap +
  consensus) with an inspectable breakdown; weak hits are flagged
- multi-query support: a list of queries is fanned out and fused into one set
- freshness signal extracted from page metadata on fetch
- signal-driven content quality (ok / thin / spa_shell / blocked) instead of
  silently returning junk, plus a verbatim excerpt pinned to char offsets
- fixed retry delays, bounded concurrent fetch, dedupe, and domain filters
"""

from typing import Optional, Dict, List, Any, Tuple
import concurrent.futures
import copy
import json
import logging
import base64
import random
import re
import threading

from ..diagnostics import report_suppressed_exception
import time
import warnings
from collections import OrderedDict
from html import unescape
from urllib.parse import parse_qs, urljoin, urlparse, urlsplit, urlunsplit

from .base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    name = "web_search"
    aliases = ("search_web", "internet_search", "websearch")
    search_hint = "search the web for candidate links"
    tool_category = "external"
    tool_tags = ("web", "search", "docs", "internet", "reference", "news")
    read_only = True
    concurrency_safe = True

    description = """Search the web for candidate links, ranked by multi-engine consensus and evidence score. Accepts one query or a list of queries. Use web_fetch to read selected pages."""

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": ["string", "array"],
                "items": {"type": "string"},
                "description": "Search query text, or a list of related queries fanned out and fused into one ranked set.",
            },
            "max_results": {"type": "integer", "description": "Max links to return (default: 10).", "default": 10},
            "fetch_content": {
                "type": "boolean",
                "description": "Also fetch and extract each result's page. Prefer web_fetch for targeted reads.",
                "default": False,
            },
            "include_domains": {"type": "array", "items": {"type": "string"}},
            "exclude_domains": {"type": "array", "items": {"type": "string"}},
            "recency": {"type": "string", "description": "Recency hint: d/w/m/y."},
            "request_timeout": {"type": "integer", "default": 15},
            "max_retries": {"type": "integer", "default": 5},
            "fetch_workers": {"type": "integer", "default": 4},
            "max_content_chars": {"type": "integer", "default": 7000},
            "output_format": {"type": "string", "enum": ["text", "markdown"], "default": "text"},
        },
        "required": ["query"],
    }

    DEFAULT_MAX_RESULTS = 10
    MAX_ALLOWED_RESULTS = 30
    MAX_QUERIES = 6
    DEFAULT_TIMEOUT = 15
    DEFAULT_MAX_RETRIES = 5
    RETRY_DELAYS_SECONDS = (1, 3, 5, 7, 15)
    DEFAULT_FETCH_WORKERS = 4
    MAX_FETCH_WORKERS = 8
    MAX_SEARCH_WORKERS = 6
    DEFAULT_MAX_CONTENT_CHARS = 7000
    MAX_CONTENT_CHARS_LIMIT = 25000
    MAX_MEDIA_ASSETS = 16
    RETRY_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504, 522, 524}
    ALLOWED_RECENCY = {"d", "w", "m", "y"}
    CACHE_SIZE = 128
    # Reciprocal Rank Fusion damping constant (standard k=60 from the IR
    # literature): score contribution of a hit at rank r is 1/(k+r), so the top
    # ranks dominate while lower ranks still contribute a little.
    RRF_K = 60
    # Engines queried in parallel. ddgs handles DuckDuckGo's bot-wall itself and
    # is the most reliable; Bing scrapes cleanly; Brave is a useful third even
    # though it rate-limits. A single engine failing barely moves the fusion.
    SEARCH_ENGINES = ("ddg", "bing", "brave")
    # Evidence-score weights (sum to 1.0): how much each deterministic signal
    # contributes to the final 0..1 confidence attached to every result.
    EVIDENCE_WEIGHTS = {"fusion": 0.45, "lexical": 0.35, "consensus": 0.20}
    # Below this evidence score a result is labelled weak so the model knows the
    # hit is thin rather than authoritative.
    WEAK_EVIDENCE_THRESHOLD = 0.18
    _STOPWORDS = frozenset(
        "a an and are as at be but by for from how if in into is it of on or "
        "that the to was what when where which who why with your you".split()
    )
    USER_AGENTS = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    )
    BLOCKED_PAGE_MARKERS = (
        "access denied",
        "captcha",
        "cf-challenge",
        "checking your browser",
        "please enable cookies",
        "security check",
        "unusual traffic",
        "verify you are human",
        "we need to verify",
        "请完成安全验证",
        "请在微信客户端打开链接",
        "当前环境异常",
        "访问环境异常",
        "验证后继续访问",
        "需要验证",
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
            report_suppressed_exception("load optional web-search provider")
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

    @classmethod
    def _normalize_queries(cls, value: Any) -> List[str]:
        """Accept a single query string or a list; return a deduped, capped list."""
        if isinstance(value, str):
            raw_items: List[Any] = [value]
        elif isinstance(value, (list, tuple)):
            raw_items = list(value)
        else:
            raw_items = [value] if value is not None else []
        queries: List[str] = []
        seen: set = set()
        for item in raw_items:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            queries.append(text)
            if len(queries) >= cls.MAX_QUERIES:
                break
        return queries

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        """Lowercase alphanumeric tokens with stopwords removed, for lexical scoring."""
        tokens = re.findall(r"[0-9a-z]+", str(text or "").lower())
        return [tok for tok in tokens if tok not in cls._STOPWORDS and len(tok) > 1]

    @classmethod
    def _lexical_overlap(cls, query_terms: set, *fields: str) -> float:
        """Fraction of distinct query terms present in the result's text (0..1)."""
        if not query_terms:
            return 0.0
        haystack = set()
        for field in fields:
            haystack.update(cls._tokenize(field))
        if not haystack:
            return 0.0
        hits = sum(1 for term in query_terms if term in haystack)
        return hits / len(query_terms)

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

    @classmethod
    def _normalize_url_or_domain(cls, value: str) -> str:
        raw = str(value or "").strip()
        if not raw or any(char.isspace() for char in raw):
            return ""
        if "://" in raw:
            return cls._normalize_url(raw)
        if "." not in raw or raw.startswith("."):
            return ""
        return cls._normalize_url(f"https://{raw}")

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
    def _compute_backoff(attempt: int) -> float:
        return float(WebSearchTool.RETRY_DELAYS_SECONDS[attempt])

    def _build_request_headers(self, url: str) -> Dict[str, str]:
        host = (urlparse(str(url or "")).hostname or "").lower()
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,text/plain;q=0.7,*/*;q=0.5",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
        }
        if host.endswith("mp.weixin.qq.com"):
            headers["Referer"] = "https://mp.weixin.qq.com/"
        return headers

    def _request_with_retry(self, url: str, *, params: Optional[Dict[str, Any]], timeout: int, max_retries: int):
        import requests
        last_response = None
        retries = len(self.RETRY_DELAYS_SECONDS)
        for attempt in range(retries + 1):
            try:
                session = self._get_http_session()
                response = session.get(
                    url,
                    params=params,
                    timeout=timeout,
                    allow_redirects=True,
                    headers=self._build_request_headers(url),
                )
                last_response = response
                if response.status_code in self.RETRY_HTTP_CODES and attempt < retries:
                    time.sleep(self._compute_backoff(attempt))
                    continue
                return response
            except requests.RequestException:
                if attempt < retries:
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

    def _run_engine(
        self,
        engine: str,
        query: str,
        max_results: int,
        recency: str,
        timeout: int,
        max_retries: int,
        include_domains: List[str],
        exclude_domains: List[str],
    ) -> List[Dict[str, Any]]:
        """Dispatch one engine by name, isolating its failure from the others."""
        try:
            if engine == "ddg":
                return self._search_ddg(query, max_results, recency, include_domains, exclude_domains)
            if engine == "bing":
                return self._search_bing(query, max_results, timeout, max_retries, include_domains, exclude_domains)
            if engine == "brave":
                return self._search_brave(query, max_results, timeout, max_retries, include_domains, exclude_domains)
        except Exception as e:  # pragma: no cover - defensive; engines already catch
            self.logger.debug(f"engine {engine} raised: {e}")
        return []

    def _gather_engine_results(
        self,
        query: str,
        max_results: int,
        recency: str,
        timeout: int,
        max_retries: int,
        include_domains: List[str],
        exclude_domains: List[str],
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """Query every engine in parallel; return per-engine rankings + attempts.

        Each engine runs concurrently and independently, so a slow or failing
        backend never blocks the others. Over-fetch per engine (2x) so the fusion
        has enough overlap to detect consensus before truncating to max_results.
        """
        per_engine_target = max_results * 2
        engines = list(self.SEARCH_ENGINES)
        results_by_engine: Dict[str, List[Dict[str, Any]]] = {}
        workers = min(self.MAX_SEARCH_WORKERS, len(engines)) or 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_engine = {
                executor.submit(
                    self._run_engine,
                    engine,
                    query,
                    per_engine_target,
                    recency,
                    timeout,
                    max_retries,
                    include_domains,
                    exclude_domains,
                ): engine
                for engine in engines
            }
            for future in concurrent.futures.as_completed(future_to_engine):
                engine = future_to_engine[future]
                try:
                    results_by_engine[engine] = future.result() or []
                except Exception as e:  # pragma: no cover - defensive
                    self.logger.debug(f"engine {engine} future failed: {e}")
                    results_by_engine[engine] = []
        attempts = [
            {"provider": engine, "count": len(results_by_engine.get(engine, [])), "status": "ok" if results_by_engine.get(engine) else "empty"}
            for engine in engines
        ]
        return results_by_engine, attempts

    def _fuse_results(
        self,
        results_by_engine: Dict[str, List[Dict[str, Any]]],
        query_terms: set,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """Merge per-engine rankings with Reciprocal Rank Fusion + evidence scoring.

        RRF sums 1/(k+rank) across the engines that returned a URL, so a hit that
        several engines rank highly wins even if no single engine put it first.
        The merged hits then get a deterministic evidence score exposing why each
        result is trusted (rank fusion, query overlap, engine consensus).
        """
        merged: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        max_rrf = 0.0
        for engine, results in results_by_engine.items():
            for item in results:
                href = str(item.get("href") or "")
                if not href:
                    continue
                rank = int(item.get("rank") or 0) or (results.index(item) + 1)
                contribution = 1.0 / (self.RRF_K + rank)
                entry = merged.get(href)
                if entry is None:
                    entry = {
                        "title": item.get("title") or href,
                        "href": href,
                        "body": item.get("body") or "",
                        "rrf": 0.0,
                        "engines": [],
                        "best_rank": rank,
                    }
                    merged[href] = entry
                entry["rrf"] += contribution
                if engine not in entry["engines"]:
                    entry["engines"].append(engine)
                if rank < entry["best_rank"]:
                    entry["best_rank"] = rank
                # Prefer the longest snippet seen across engines.
                if len(str(item.get("body") or "")) > len(str(entry.get("body") or "")):
                    entry["body"] = item.get("body") or ""
                if not entry.get("title") and item.get("title"):
                    entry["title"] = item.get("title")
                max_rrf = max(max_rrf, entry["rrf"])

        engine_count = max(1, len([e for e, r in results_by_engine.items() if r]))
        fused: List[Dict[str, Any]] = []
        for entry in merged.values():
            fusion_norm = (entry["rrf"] / max_rrf) if max_rrf > 0 else 0.0
            lexical = self._lexical_overlap(query_terms, entry.get("title", ""), entry.get("body", ""))
            consensus = len(entry["engines"]) / engine_count
            evidence = (
                self.EVIDENCE_WEIGHTS["fusion"] * fusion_norm
                + self.EVIDENCE_WEIGHTS["lexical"] * lexical
                + self.EVIDENCE_WEIGHTS["consensus"] * consensus
            )
            entry["evidence_score"] = round(evidence, 4)
            entry["evidence"] = {
                "fusion": round(fusion_norm, 4),
                "lexical": round(lexical, 4),
                "consensus": round(consensus, 4),
                "engines": list(entry["engines"]),
            }
            entry["weak"] = evidence < self.WEAK_EVIDENCE_THRESHOLD
            fused.append(entry)

        # Sort by evidence, then engine consensus, then best rank as tiebreakers.
        fused.sort(key=lambda e: (e["evidence_score"], len(e["engines"]), -e["best_rank"]), reverse=True)
        for idx, entry in enumerate(fused[:max_results], 1):
            entry["rank"] = idx
            entry["body"] = self._truncate_text(str(entry.get("body") or ""), 360)
            entry.pop("rrf", None)
            entry.pop("best_rank", None)
        return fused[:max_results]

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
    def _unwrap_bing_url(href: str) -> str:
        """Resolve a Bing `bing.com/ck/a?...&u=a1<base64>` redirect to its target.

        Bing wraps every organic result in a tracking redirect whose real
        destination is base64 (urlsafe) in the `u` param, prefixed with `a1`.
        Left unwrapped, every Bing hit is a bing.com URL -- useless for fetching
        and impossible to fuse with other engines by consensus.
        """
        raw = str(href or "").strip()
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if not (host.endswith("bing.com") and "/ck/a" in parsed.path):
            return raw
        params = parse_qs(parsed.query)
        token = (params.get("u") or [""])[0]
        if not token:
            return raw
        if token[:2].lower() == "a1":
            token = token[2:]
        token = token + "=" * (-len(token) % 4)
        try:
            decoded = base64.urlsafe_b64decode(token).decode("utf-8", "replace")
        except Exception:
            report_suppressed_exception("decode bing redirect url")
            return raw
        return decoded if decoded.startswith(("http://", "https://")) else raw

    def _search_bing(
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
                "https://www.bing.com/search",
                params={"q": query, "setlang": "en"},
                timeout=timeout,
                max_retries=max_retries,
            )
            if response is None or response.status_code != 200:
                return []
            soup = BeautifulSoup(response.text, "html.parser")
            raw_results: List[Dict[str, str]] = []
            for block in soup.select("li.b_algo"):
                if len(raw_results) >= max_results * 2:
                    break
                link = block.select_one("h2 a[href], a[href]")
                if not link:
                    continue
                snippet_node = block.select_one(".b_caption p, p")
                raw_results.append(
                    {
                        "title": self._clean_text(link.get_text(" ", strip=True)),
                        "href": self._unwrap_bing_url(str(link.get("href") or "")),
                        "body": self._clean_text(snippet_node.get_text(" ", strip=True) if snippet_node else block.get_text(" ", strip=True)),
                    }
                )
            return self._normalize_search_results(raw_results, max_results, include_domains, exclude_domains)
        except Exception as e:
            self.logger.debug(f"Bing search failed: {e}")
            return []

    @staticmethod
    def _first_meta_content(soup, *selectors: str) -> str:
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue
            content = str(node.get("content") or "").strip()
            if content:
                return content
        return ""

    @classmethod
    def _extract_script_string(cls, html_text: str, variable_name: str) -> str:
        pattern = re.compile(
            rf"\b(?:var\s+)?{re.escape(variable_name)}\s*=\s*(['\"])(.*?)\1",
            re.DOTALL,
        )
        match = pattern.search(html_text or "")
        if not match:
            return ""
        value = match.group(2)
        if "\\" in value:
            try:
                value = bytes(value, "utf-8").decode("unicode_escape")
            except Exception:
                report_suppressed_exception("decode escaped web-search value")
        return unescape(value).strip()

    @classmethod
    def _extract_metadata(cls, soup) -> Dict[str, str]:
        html_text = str(soup)
        title_candidates = [
            cls._first_meta_content(
                soup,
                'meta[property="og:title"]',
                'meta[name="twitter:title"]',
                'meta[name="title"]',
            ),
            soup.title.string.strip() if soup.title and soup.title.string else "",
            soup.select_one("#activity-name").get_text(" ", strip=True) if soup.select_one("#activity-name") else "",
            soup.select_one(".rich_media_title").get_text(" ", strip=True) if soup.select_one(".rich_media_title") else "",
            cls._extract_script_string(html_text, "msg_title"),
        ]
        desc_candidates = [
            cls._first_meta_content(
                soup,
                'meta[name="description"]',
                'meta[property="og:description"]',
                'meta[name="twitter:description"]',
            ),
            cls._extract_script_string(html_text, "msg_desc"),
        ]
        site_name = cls._first_meta_content(soup, 'meta[property="og:site_name"]')
        author = cls._first_meta_content(soup, 'meta[name="author"]', 'meta[property="og:article:author"]')
        title = next((cls._clean_text(item) for item in title_candidates if cls._clean_text(item)), "")
        desc = next((cls._clean_text(item) for item in desc_candidates if cls._clean_text(item)), "")
        return {
            "title": title,
            "description": desc,
            "site_name": cls._clean_text(site_name),
            "author": cls._clean_text(author),
            "published_at": cls._extract_published_at(soup),
        }

    # ISO-8601-ish date, matching 2024-01-31 and 2024-01-31T12:00:00Z forms.
    _ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?)\b")

    @classmethod
    def _extract_published_at(cls, soup) -> str:
        """Best-effort publish date from meta tags, JSON-LD, or <time> elements."""
        meta = cls._first_meta_content(
            soup,
            'meta[property="article:published_time"]',
            'meta[name="article:published_time"]',
            'meta[property="og:published_time"]',
            'meta[name="pubdate"]',
            'meta[name="publishdate"]',
            'meta[name="date"]',
            'meta[itemprop="datePublished"]',
        )
        if meta:
            match = cls._ISO_DATE_RE.search(meta)
            if match:
                return match.group(1)
        # JSON-LD structured data (schema.org Article etc.)
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text() or ""
            match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', raw)
            if match:
                iso = cls._ISO_DATE_RE.search(match.group(1))
                if iso:
                    return iso.group(1)
        # <time datetime="...">
        time_node = soup.find("time")
        if time_node:
            candidate = str(time_node.get("datetime") or time_node.get_text(" ", strip=True) or "")
            match = cls._ISO_DATE_RE.search(candidate)
            if match:
                return match.group(1)
        return ""

    @classmethod
    def _classify_content_quality(cls, content: str, main_node) -> str:
        """Label extracted content so the model knows what it is standing on.

        - blocked: caller already detected an anti-bot / verification wall
        - spa_shell: almost no text but plenty of script/app markup (JS app that
          never rendered server-side) -> the text we have is not the real page
        - thin: real but short (a stub, a nav page, a redirect notice)
        - ok: substantial readable content
        """
        text = str(content or "").strip()
        length = len(text)
        if length >= 1200:
            return "ok"
        # Distinguish a short-but-real page from an unrendered JS shell.
        if main_node is not None:
            try:
                script_markup = sum(len(str(s)) for s in main_node.find_all("script"))
            except Exception:
                script_markup = 0
            if length < 200 and script_markup > 2000:
                return "spa_shell"
        if length < 400:
            return "thin"
        return "ok"

    @classmethod
    def _build_excerpt(cls, content: str, query_terms: set, max_len: int = 320) -> Dict[str, Any]:
        """Pin a verbatim excerpt (with char offsets) around the best query match.

        Offsets index into the returned ``fetched_content`` so a caller can quote
        an exact span. Falls back to the head of the content when nothing matches.
        """
        text = str(content or "")
        if not text:
            return {}
        lowered = text.lower()
        best_pos = -1
        for term in sorted(query_terms, key=len, reverse=True):
            pos = lowered.find(term)
            if pos != -1:
                best_pos = pos
                break
        if best_pos == -1:
            start = 0
        else:
            start = max(0, best_pos - max_len // 3)
        end = min(len(text), start + max_len)
        # Snap to word boundaries so the excerpt reads cleanly.
        if start > 0:
            space = text.find(" ", start)
            if 0 <= space < end:
                start = space + 1
        excerpt = text[start:end].strip()
        return {"text": excerpt, "start": start, "end": start + len(excerpt)}

    def _extract_media_assets(self, soup, base_url: str, limit: int = MAX_MEDIA_ASSETS) -> List[Dict[str, str]]:
        assets: List[Dict[str, str]] = []
        seen = set()

        def add_asset(asset_type: str, raw_url: Any, *, label: str = "", source: str = "", width: Any = "", height: Any = "") -> None:
            if len(assets) >= limit:
                return
            url_text = unescape(str(raw_url or "").strip())
            if not url_text or url_text.startswith("data:"):
                return
            url = self._normalize_url(urljoin(base_url, url_text))
            if not url or url in seen:
                return
            seen.add(url)
            item = {
                "type": asset_type,
                "url": url,
                "label": self._truncate_text(self._clean_text(str(label or "")), 180),
                "source": source,
            }
            if width:
                item["width"] = str(width)
            if height:
                item["height"] = str(height)
            assets.append(item)

        for selector in ('meta[property="og:image"]', 'meta[name="twitter:image"]', 'meta[property="og:video"]'):
            for node in soup.select(selector):
                add_asset("video" if "video" in selector else "image", node.get("content"), source=selector)

        for img in soup.find_all("img"):
            raw_url = ""
            source_attr = ""
            for attr in ("data-src", "data-original", "data-actualsrc", "data-backsrc", "src"):
                candidate = img.get(attr)
                if candidate:
                    raw_url = candidate
                    source_attr = attr
                    break
            label = img.get("alt") or img.get("title") or img.get("data-caption") or img.get("data-type") or ""
            add_asset(
                "image",
                raw_url,
                label=label,
                source=f"img:{source_attr}" if source_attr else "img",
                width=img.get("data-w") or img.get("width") or "",
                height=img.get("data-h") or img.get("height") or "",
            )

        for node in soup.find_all(["video", "source"]):
            add_asset("video", node.get("src") or node.get("data-src"), label=node.get("type") or "", source=node.name)
            if node.name == "video":
                add_asset("image", node.get("poster"), label="video poster", source="video:poster")

        return assets

    def _select_main_node(self, soup):
        best_node = None
        best_score = -1
        selectors = [
            "#js_content",
            ".rich_media_content",
            "article",
            "main",
            "[role='main']",
            ".content",
            ".post-content",
            ".entry-content",
            "#content",
            "#main",
            ".main",
            ".markdown-body",
        ]
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

    def _is_likely_blocked_page(self, content: str, metadata: Dict[str, str]) -> bool:
        text = "\n".join(
            str(value or "")
            for value in (
                metadata.get("title"),
                metadata.get("description"),
                content,
            )
        ).lower()
        if not text.strip():
            return False
        return any(marker in text for marker in self.BLOCKED_PAGE_MARKERS)

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
        query_terms: Optional[set] = None,
    ) -> Dict[str, Any]:
        from bs4 import BeautifulSoup

        query_terms = query_terms or set()
        normalized_url = self._normalize_url(url)
        if not normalized_url:
            return {"fetch_status": "error", "content_quality": "error", "fetched_content": "[Error: Invalid URL]", "fetched_title": "", "fetched_description": "", "outbound_links": []}
        try:
            response = self._request_with_retry(normalized_url, params=None, timeout=timeout, max_retries=max_retries)
        except Exception as e:
            return {"fetch_status": "error", "content_quality": "error", "fetched_content": f"[Error: {str(e)}]", "fetched_title": "", "fetched_description": "", "outbound_links": []}
        if response is None or response.status_code >= 400:
            status = response.status_code if response is not None else "N/A"
            return {"fetch_status": "error", "content_quality": "error", "fetched_content": f"[Error: HTTP {status}]", "fetched_title": "", "fetched_description": "", "outbound_links": []}

        content_type = str(response.headers.get("content-type") or "").lower()
        if "text/html" not in content_type and ("application/json" in content_type or "text/" in content_type):
            content = self._clean_text(response.text, keep_newlines=(output_format == "markdown"))
            content = content or "[No readable text found]"
            truncated = self._truncate_text(content, max_content_chars)
            return {
                "fetch_status": "ok",
                "content_quality": self._classify_content_quality(content, None),
                "fetched_content": truncated,
                "fetched_title": "",
                "fetched_description": "",
                "outbound_links": [],
                "media_assets": [],
                "published_at": "",
                "excerpt": self._build_excerpt(truncated, query_terms),
            }

        soup = BeautifulSoup(response.content, "html.parser")
        metadata = self._extract_metadata(soup)
        media_assets = self._extract_media_assets(soup, normalized_url)
        # Capture the pre-strip main node so an unrendered JS app (lots of
        # <script>, almost no text) can be told apart from a genuinely thin page.
        pre_strip_main = self._select_main_node(soup)
        for tag in soup(["script", "style", "noscript", "iframe", "img", "video", "audio", "svg", "nav", "header", "footer", "form", "aside", "button", "canvas"]):
            tag.decompose()
        main = self._select_main_node(soup)
        if main is None:
            return {
                "fetch_status": "error",
                "content_quality": "error",
                "fetched_content": "[No readable text found]",
                "fetched_title": metadata["title"],
                "fetched_description": metadata["description"],
                "published_at": metadata.get("published_at", ""),
                "outbound_links": [],
                "media_assets": media_assets,
            }
        if output_format == "markdown":
            content = self._clean_text(main.get_text("\n", strip=True), keep_newlines=True)
        else:
            content = self._clean_text(main.get_text(" ", strip=True), keep_newlines=False)
        if not content:
            content = "[No readable text found]"
        if self._is_likely_blocked_page(content, metadata):
            fetch_status = "blocked"
            content_quality = "blocked"
            content = (
                "[Blocked or verification-gated page: fetched content appears to be an access check, "
                "captcha, app-only prompt, or anti-bot page. Metadata and media assets are included when available.]"
            )
        else:
            fetch_status = "ok"
            content_quality = self._classify_content_quality(content, pre_strip_main)
        truncated = self._truncate_text(content, max_content_chars)
        return {
            "fetch_status": fetch_status,
            "content_quality": content_quality,
            "fetched_content": truncated,
            "fetched_title": self._clean_text(metadata["title"]),
            "fetched_description": self._truncate_text(self._clean_text(metadata["description"]), 500),
            "fetched_site_name": self._clean_text(metadata.get("site_name", "")),
            "fetched_author": self._clean_text(metadata.get("author", "")),
            "published_at": self._clean_text(metadata.get("published_at", "")),
            "outbound_links": self._extract_links(main, normalized_url),
            "media_assets": media_assets,
            "excerpt": {} if fetch_status == "blocked" else self._build_excerpt(truncated, query_terms),
        }

    def get_execution_message(self, **kwargs) -> str:
        queries = self._normalize_queries(kwargs.get("query"))
        max_results = kwargs.get("max_results", self.DEFAULT_MAX_RESULTS)
        if queries:
            label = queries[0]
            if len(label) > 72:
                label = f"{label[:69]}..."
            if len(queries) > 1:
                label = f"{label} (+{len(queries) - 1} more)"
            return f"Executing web_search: {label} (max_results={max_results})"
        return "Executing web_search..."

    def _search_one_query(
        self,
        query: str,
        max_results: int,
        recency: str,
        request_timeout: int,
        max_retries: int,
        include_domains: List[str],
        exclude_domains: List[str],
    ) -> Dict[str, Any]:
        """Run one query across every engine in parallel, cache, and fuse."""
        direct_url = self._normalize_url_or_domain(query)
        if direct_url and self._passes_domain_filters(direct_url, include_domains, exclude_domains):
            return {
                "results": [
                    {
                        "title": direct_url,
                        "href": direct_url,
                        "body": "Direct URL supplied; use web_fetch for readable page content.",
                        "rank": 1,
                        "evidence_score": 1.0,
                        "evidence": {"fusion": 1.0, "lexical": 1.0, "consensus": 1.0, "engines": ["direct_url"]},
                        "engines": ["direct_url"],
                        "weak": False,
                    }
                ],
                "engine": "direct_url",
                "attempts": [{"provider": "direct_url", "count": 1, "status": "ok"}],
                "cached": False,
            }

        cache_key = json.dumps(
            {"q": query, "n": max_results, "recency": recency, "inc": include_domains, "exc": exclude_domains},
            sort_keys=True,
            ensure_ascii=False,
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            cached = dict(cached)
            cached["cached"] = True
            return cached

        results_by_engine, attempts = self._gather_engine_results(
            query, max_results, recency, request_timeout, max_retries, include_domains, exclude_domains
        )
        query_terms = set(self._tokenize(query))
        fused = self._fuse_results(results_by_engine, query_terms, max_results)
        used = [a["provider"] for a in attempts if a.get("count")]
        engine = "+".join(used) if used else "none"
        payload = {"results": fused, "engine": engine, "attempts": attempts, "cached": False}
        self._cache_put(cache_key, payload)
        return payload

    def execute(self, **kwargs) -> ToolResult:
        if not self._available:
            return ToolResult.fail("Missing dependencies. Install: pip install requests beautifulsoup4 ddgs")

        queries = self._normalize_queries(kwargs.get("query"))
        if not queries:
            return ToolResult.fail("Query is required")

        max_results = self._coerce_int(kwargs.get("max_results", self.DEFAULT_MAX_RESULTS), self.DEFAULT_MAX_RESULTS, 1, self.MAX_ALLOWED_RESULTS)
        fetch_content = self._coerce_bool(kwargs.get("fetch_content"), False)
        include_domains = self._normalize_domain_list(kwargs.get("include_domains"))
        exclude_domains = self._normalize_domain_list(kwargs.get("exclude_domains"))
        recency = str(kwargs.get("recency") or "").strip().lower()
        if recency not in self.ALLOWED_RECENCY:
            recency = ""
        request_timeout = self._coerce_int(kwargs.get("request_timeout", self.DEFAULT_TIMEOUT), self.DEFAULT_TIMEOUT, 5, 90)
        max_retries = self.DEFAULT_MAX_RETRIES
        fetch_workers = self._coerce_int(kwargs.get("fetch_workers", self.DEFAULT_FETCH_WORKERS), self.DEFAULT_FETCH_WORKERS, 1, self.MAX_FETCH_WORKERS)
        max_content_chars = self._coerce_int(kwargs.get("max_content_chars", self.DEFAULT_MAX_CONTENT_CHARS), self.DEFAULT_MAX_CONTENT_CHARS, 1000, self.MAX_CONTENT_CHARS_LIMIT)
        output_format = str(kwargs.get("output_format") or "text").strip().lower()
        if output_format not in {"text", "markdown"}:
            output_format = "text"

        # Fan out each query (each query itself fans out across engines), then
        # fuse everything into one ranked set so a query list broadens coverage.
        per_query = [
            self._search_one_query(q, max_results, recency, request_timeout, max_retries, include_domains, exclude_domains)
            for q in queries
        ]
        combined_terms: set = set()
        for q in queries:
            combined_terms.update(self._tokenize(q))

        # Re-fuse across queries by treating each query's ranked list as an
        # engine ranking, so a URL surfaced by several queries rises.
        cross: Dict[str, List[Dict[str, Any]]] = {}
        attempts: List[Dict[str, Any]] = []
        any_cached = False
        for idx, payload in enumerate(per_query):
            cross[f"query{idx}"] = payload.get("results", [])
            any_cached = any_cached or payload.get("cached", False)
            for attempt in payload.get("attempts", []):
                attempts.append({**attempt, "query": queries[idx]})
        if len(queries) == 1:
            results = per_query[0].get("results", [])
            engine = per_query[0].get("engine", "none")
        else:
            results = self._fuse_results(cross, combined_terms, max_results)
            engine = "multi-query"

        if not results:
            provider_names = ", ".join(sorted({a.get("provider", "") for a in attempts if a.get("provider")})) or "configured providers"
            return ToolResult.ok(
                f"No results found for: {'; '.join(queries)} (checked {provider_names})",
                data={"count": 0, "results": [], "engine": "none", "attempts": attempts, "cached": any_cached, "queries": queries},
            )

        if fetch_content:
            workers = min(fetch_workers, len(results))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_index = {
                    executor.submit(self._fetch_page_payload, res["href"], request_timeout, max_retries, max_content_chars, output_format, combined_terms): i
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
        weak_count = sum(1 for r in results if r.get("weak"))
        header_query = "; ".join(queries)
        output_parts = [
            f"# Search Results for: {header_query}",
            f"**Engines:** {engine}",
            f"**Backend Attempts:** {summary}",
            f"**Search Cache:** {'hit' if any_cached else 'miss'}",
        ]
        if weak_count:
            output_parts.append(f"**Low-confidence results:** {weak_count} of {len(results)} (evidence < {self.WEAK_EVIDENCE_THRESHOLD})")
        output_parts.append("")
        for i, res in enumerate(results, 1):
            weak_tag = "  _(low confidence)_" if res.get("weak") else ""
            output_parts.append(f"## {i}. {res.get('title', 'No Title')}{weak_tag}")
            output_parts.append(f"**Source:** {res.get('href', '#')}")
            ev = res.get("evidence") or {}
            if res.get("evidence_score") is not None:
                engines = ", ".join(ev.get("engines", [])) or "n/a"
                output_parts.append(
                    f"**Evidence:** {res.get('evidence_score')} "
                    f"(fusion {ev.get('fusion', 0)}, overlap {ev.get('lexical', 0)}, consensus {ev.get('consensus', 0)}; engines: {engines})"
                )
            output_parts.append(f"**Snippet:** {res.get('body', '')}")
            if fetch_content:
                output_parts.append(f"**Fetch Status:** {res.get('fetch_status', 'n/a')}")
                if res.get("content_quality"):
                    output_parts.append(f"**Content Quality:** {res.get('content_quality')}")
                if res.get("fetched_title"):
                    output_parts.append(f"**Page Title:** {res.get('fetched_title')}")
                if res.get("fetched_description"):
                    output_parts.append(f"**Page Description:** {res.get('fetched_description')}")
                if res.get("fetched_author"):
                    output_parts.append(f"**Author:** {res.get('fetched_author')}")
                if res.get("fetched_site_name"):
                    output_parts.append(f"**Site:** {res.get('fetched_site_name')}")
                if res.get("published_at"):
                    output_parts.append(f"**Published:** {res.get('published_at')}")
                links = res.get("outbound_links") or []
                if links:
                    output_parts.append("**Outbound Links (sample):**")
                    for link in links[:6]:
                        output_parts.append(f"- {link}")
                media_assets = res.get("media_assets") or []
                if media_assets:
                    output_parts.append("**Media Assets (sample):**")
                    for asset in media_assets[:8]:
                        label = f" - {asset.get('label')}" if asset.get("label") else ""
                        output_parts.append(f"- {asset.get('type', 'media')}: {asset.get('url')}{label}")
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
                "queries": queries,
                "attempts": attempts,
                "cached": any_cached,
                "weak_count": weak_count,
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


class WebFetchTool(WebSearchTool):
    name = "web_fetch"
    aliases = ("fetch_web", "webfetch", "fetch_url", "fetch_page")
    search_hint = "fetch readable content from selected web links"
    tool_tags = ("web", "fetch", "docs", "internet", "reference", "page")

    description = """Fetch readable content from one or more URLs selected from web_search results."""

    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Single URL to fetch."},
            "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to fetch, up to 8."},
            "query": {"type": "string", "description": "Optional focus query; pins the returned excerpt to the best-matching passage."},
            "request_timeout": {"type": "integer", "default": 15},
            "max_retries": {"type": "integer", "default": 5},
            "max_content_chars": {"type": "integer", "default": 12000},
            "output_format": {"type": "string", "enum": ["text", "markdown"], "default": "markdown"},
        },
    }

    DEFAULT_MAX_CONTENT_CHARS = 12000
    MAX_URLS = 8

    def get_execution_message(self, **kwargs) -> str:
        urls = self._normalize_url_inputs(kwargs)
        if len(urls) == 1:
            return f"Executing web_fetch: {urls[0]}"
        if urls:
            return f"Executing web_fetch: {len(urls)} URLs"
        return "Executing web_fetch..."

    def _normalize_url_inputs(self, kwargs: Dict[str, Any]) -> List[str]:
        raw_urls: List[Any] = []
        if kwargs.get("url"):
            raw_urls.append(kwargs.get("url"))
        urls_value = kwargs.get("urls")
        if isinstance(urls_value, str):
            raw_urls.append(urls_value)
        elif isinstance(urls_value, list):
            raw_urls.extend(urls_value)

        normalized: List[str] = []
        seen = set()
        for raw_url in raw_urls:
            url = self._normalize_url(str(raw_url or "").strip())
            if not url or url in seen:
                continue
            seen.add(url)
            normalized.append(url)
            if len(normalized) >= self.MAX_URLS:
                break
        return normalized

    def execute(self, **kwargs) -> ToolResult:
        if not self._available:
            return ToolResult.fail("Missing dependencies. Install: pip install requests beautifulsoup4 ddgs")

        urls = self._normalize_url_inputs(kwargs)
        if not urls:
            return ToolResult.fail("url or urls is required")

        request_timeout = self._coerce_int(kwargs.get("request_timeout", self.DEFAULT_TIMEOUT), self.DEFAULT_TIMEOUT, 5, 90)
        max_retries = self.DEFAULT_MAX_RETRIES
        max_content_chars = self._coerce_int(kwargs.get("max_content_chars", self.DEFAULT_MAX_CONTENT_CHARS), self.DEFAULT_MAX_CONTENT_CHARS, 1000, self.MAX_CONTENT_CHARS_LIMIT)
        output_format = str(kwargs.get("output_format") or "markdown").strip().lower()
        if output_format not in {"text", "markdown"}:
            output_format = "markdown"

        query_terms = set(self._tokenize(kwargs.get("query") or ""))

        results: List[Dict[str, Any]] = []
        for url in urls:
            payload = self._fetch_page_payload(
                url,
                timeout=request_timeout,
                max_retries=max_retries,
                max_content_chars=max_content_chars,
                output_format=output_format,
                query_terms=query_terms,
            )
            item = {"url": url}
            item.update(payload)
            results.append(item)

        output_parts = ["# Web Fetch Results", ""]
        for index, result in enumerate(results, 1):
            output_parts.append(f"## {index}. {result.get('fetched_title') or result.get('url')}")
            output_parts.append(f"**URL:** {result.get('url')}")
            output_parts.append(f"**Fetch Status:** {result.get('fetch_status', 'n/a')}")
            if result.get("content_quality"):
                output_parts.append(f"**Content Quality:** {result.get('content_quality')}")
            if result.get("fetched_description"):
                output_parts.append(f"**Page Description:** {result.get('fetched_description')}")
            if result.get("fetched_author"):
                output_parts.append(f"**Author:** {result.get('fetched_author')}")
            if result.get("fetched_site_name"):
                output_parts.append(f"**Site:** {result.get('fetched_site_name')}")
            if result.get("published_at"):
                output_parts.append(f"**Published:** {result.get('published_at')}")
            links = result.get("outbound_links") or []
            if links:
                output_parts.append("**Outbound Links (sample):**")
                for link in links[:6]:
                    output_parts.append(f"- {link}")
            media_assets = result.get("media_assets") or []
            if media_assets:
                output_parts.append("**Media Assets (sample):**")
                for asset in media_assets[:8]:
                    label = f" - {asset.get('label')}" if asset.get("label") else ""
                    output_parts.append(f"- {asset.get('type', 'media')}: {asset.get('url')}{label}")
            content = str(result.get("fetched_content") or "")
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
                "settings": {
                    "request_timeout": request_timeout,
                    "max_retries": max_retries,
                    "max_content_chars": max_content_chars,
                    "output_format": output_format,
                },
            },
        )
