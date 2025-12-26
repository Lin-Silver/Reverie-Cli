"""
Web Search Tool - Integrated Search and Content Fetching

Uses DuckDuckGo Search and Brave Search as fallback to find results,
and optionally fetches the full content of the top results.
"""

from typing import Optional, Dict, List, Any
import logging
import os
import re
import concurrent.futures
from .base import BaseTool, ToolResult

class WebSearchTool(BaseTool):
    """
    Advanced web search tool that finds links and extracts page content.
    
    Features:
    - Multi-engine support: DuckDuckGo (primary) and Brave Search (fallback)
    - Fetches and cleans webpage content (like a "read mode")
    - Integrates search and fetch in one step
    - Detailed logging to web_search_debug.log
    """
    
    name = "web_search"
    
    description = """Search the web and extract content from results.

Use this to:
- Find answers with full context
- Research topics deeply (returns page content, not just snippets)
- Look up documentation
- Get up-to-date information

Examples:
- Search & Fetch: {"query": "python 3.12 new features"}
- specific site: {"query": "site:docs.python.org asyncio"}
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5
            },
            "fetch_content": {
                "type": "boolean",
                "description": "Whether to fetch full page content (default: true)",
                "default": True
            }
        },
        "required": ["query"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._check_deps()
        self._setup_logging()
        
    def _setup_logging(self):
        self.logger = logging.getLogger("reverie.tools.web_search")
        self.logger.setLevel(logging.DEBUG)
        
        # Prevent adding multiple handlers
        if not self.logger.handlers:
            # No file handler needed as per user request to stop generating log files
            pass

    def _check_deps(self) -> None:
        """Check for required dependencies"""
        self._available = True
        try:
            import requests
            import bs4
            # duckduckgo_search is optional-ish (we can fallback to brave) 
            # but preferred
        except ImportError:
            self._available = False
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text"""
        if not text: return ""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove base64 images
        text = re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+', '', text)
        return text.strip()

    def _fetch_page_content(self, url: str, timeout: int = 15) -> str:
        """Fetch and extract main content from a URL"""
        import requests
        from bs4 import BeautifulSoup
        
        self.logger.debug(f"Fetching content from: {url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code >= 400:
                self.logger.warning(f"Failed to fetch {url}: Status {response.status_code}")
                return f"[Error: HTTP {response.status_code}]"
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove noise
            for tag in soup(['script', 'style', 'noscript', 'iframe', 'img', 'video', 'audio', 'svg', 'nav', 'header', 'footer', 'form', 'aside']):
                tag.decompose()
                
            # Try to identify main content area
            main_content = ""
            selectors = [
                'article', 'main', '[role="main"]', 
                '.content', '.post-content', '.entry-content', 
                '#content', '#main', '.main'
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    main_content = element.get_text()
                    break
            
            # Fallback to body
            if not main_content and soup.body:
                main_content = soup.body.get_text()
                
            cleaned = self._clean_text(main_content)
            
            return cleaned
            
        except Exception as e:
            self.logger.error(f"Exception fetching {url}: {e}")
            return f"[Error: {str(e)}]"

    def _search_ddg(self, query: str, max_results: int) -> List[Dict]:
        """Search using DuckDuckGo"""
        self.logger.info("Attempting DuckDuckGo Search...")
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                ddgs_gen = ddgs.text(query, max_results=max_results)
                if ddgs_gen:
                    results = list(ddgs_gen)
            self.logger.info(f"DDG found {len(results)} results")
            return results
        except Exception as e:
            self.logger.warning(f"DDG Search failed: {e}")
            return []

    def _search_brave(self, query: str, max_results: int) -> List[Dict]:
        """Search using Brave (Scraper)"""
        self.logger.info("Attempting Brave Search (Fallback)...")
        import requests
        from bs4 import BeautifulSoup
        
        url = "https://search.brave.com/search"
        params = {'q': query}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept-Encoding': 'gzip, deflate' # Avoid brotli if not supported
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15)
            if response.status_code != 200:
                self.logger.warning(f"Brave Search failed with status {response.status_code}")
                return []
                
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # Brave results usually in 'snippet' class
            snippets = soup.select('.snippet')
            if not snippets:
                snippets = soup.select('div[class*="snippet"]')
            
            for res in snippets:
                if len(results) >= max_results:
                    break
                
                title_elem = res.select_one('.title') or res.select_one('a')
                if not title_elem: continue
                
                title = title_elem.get_text(strip=True)
                
                # Link extraction
                link_elem = title_elem if title_elem.name == 'a' else title_elem.find('a')
                if not link_elem:
                    link_elem = res.select_one('a')
                
                href = link_elem['href'] if link_elem else ''
                
                if href and title:
                    results.append({
                        'title': title,
                        'href': href,
                        'body': res.get_text(strip=True)[:200] # Simple snippet
                    })
                    
            self.logger.info(f"Brave found {len(results)} results")
            return results
            
        except Exception as e:
            self.logger.error(f"Brave Search exception: {e}")
            return []

    def execute(self, **kwargs) -> ToolResult:
        if not self._available:
             return ToolResult.fail(
                "Missing dependencies. Install: pip install requests beautifulsoup4 duckduckgo-search"
            )

        query = kwargs.get('query')
        max_results = kwargs.get('max_results', 5)
        fetch_content = kwargs.get('fetch_content', True)
        
        if not query:
            return ToolResult.fail("Query is required")
            
        self.logger.info(f"Starting search: '{query}' (max: {max_results}, fetch: {fetch_content})")
        
        # 1. Try DuckDuckGo
        results = self._search_ddg(query, max_results)
        
        # 2. Fallback to Brave if DDG failed or returned 0 results
        if not results:
            self.logger.warning("DDG yielded no results, trying Brave...")
            results = self._search_brave(query, max_results)
            
        if not results:
            return ToolResult.ok(f"No results found for: {query} (Checked DDG and Brave)", data={'count': 0})
        
        # 3. Fetch content if requested
        if fetch_content:
            self.logger.info("Fetching content for results...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_result = {
                    executor.submit(self._fetch_page_content, r.get('href')):
                    r 
                    for r in results
                }
                
                for future in concurrent.futures.as_completed(future_to_result):
                    result = future_to_result[future]
                    try:
                        content = future.result()
                        result['fetched_content'] = content
                    except Exception as exc:
                        self.logger.error(f"Concurrent fetch failed: {exc}")
                        result['fetched_content'] = "[Error fetching content]"
                        
        # 4. Format Output
        output_parts = [f"# Search Results for: {query}", ""]
        
        for i, res in enumerate(results, 1):
            title = res.get('title', 'No Title')
            href = res.get('href', '#')
            body = res.get('body', '')
            content = res.get('fetched_content', '')
            
            output_parts.append(f"## {i}. {title}")
            output_parts.append(f"**Source:** {href}")
            output_parts.append(f"**Snippet:** {body}")
            
            if fetch_content and content:
                output_parts.append("\n**Extracted Content:**")
                output_parts.append("```text")
                output_parts.append(content)
                output_parts.append("```")
            
            output_parts.append("---")
        
        return ToolResult.ok(
            "\n".join(output_parts),
            data={'count': len(results), 'results': results}
        )
