"""Collect ``t.co`` links from brand replies and resolve the most frequent ones over HTTP (one-time).

Resolution is the only network activity in the data pipeline. It is injectable (``fetch=``) so tests
never touch the network, and every exception is caught per link so a flaky host cannot abort the run.
"""

from __future__ import annotations

import html
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from cadence.data.clean import clean_text
from cadence.utils.log import get_logger
from cadence.utils.text import normalize_ws

log = get_logger(__name__)

USER_AGENT = "Cadence/0.1 (+https://github.com/GODOSTROYER/cadence; one-time research link resolver)"
MAX_HTML_BYTES = 64 * 1024
DEFAULT_TIMEOUT = 8.0
DEFAULT_WORKERS = 8
DEFAULT_TOP_N = 150

_TCO_RE = re.compile(r"^https?://t\.co/[A-Za-z0-9]+$")
_SHORTENER_HOSTS: frozenset[str] = frozenset(
    {"t.co", "spoti.fi", "bit.ly", "goo.gl", "ow.ly", "tinyurl.com", "buff.ly"}
)
RETRY_WORKERS = 2
"""Worker count for the retry pass (failures are usually connect timeouts from hammering one host)."""
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class LinkResolution:
    """Result of following one short link."""

    url: str | None
    title: str | None
    status: int | None
    original_url: str | None = None
    chain: tuple[str, ...] = ()
    error: str | None = None


Fetcher = Callable[[str], LinkResolution]


def collect_links(texts: Iterable[str | None]) -> Counter[str]:
    """Count every ``t.co`` URL appearing in ``texts`` (brand replies)."""
    counts: Counter[str] = Counter()
    for text in texts:
        for link in clean_text(text, "brand").links:
            if _TCO_RE.match(link):
                counts[link] += 1
    return counts


def extract_title(document: str | bytes | None) -> str | None:
    """Return the ``<title>`` of an HTML document (first 64 KB only), or ``None``."""
    if document is None:
        return None
    if isinstance(document, bytes):
        document = document[:MAX_HTML_BYTES].decode("utf-8", errors="replace")
    match = _TITLE_RE.search(document[:MAX_HTML_BYTES])
    if not match:
        return None
    title = normalize_ws(html.unescape(match.group(1)))
    return title or None


def _is_html(response: Any) -> bool:
    return "text/html" in (response.headers.get("content-type") or "").lower()


def _redirect_chain(response: Any) -> tuple[str, ...]:
    """Every URL visited, from the ``t.co`` link to the final response."""
    history = list(getattr(response, "history", None) or [])
    return tuple(h.url for h in history) + (response.url,)


def _original_url(chain: tuple[str, ...]) -> str | None:
    """The first URL after the ``t.co`` hop, i.e. the link the brand actually shared in 2017."""
    if len(chain) > 1:
        return chain[1]
    return chain[0] if chain else None


def _is_shortener(url: str | None) -> bool:
    return bool(url) and urlsplit(url).netloc.lower() in _SHORTENER_HOSTS


def is_homepage(url: str | None) -> bool:
    """True when ``url`` has no path beyond ``/`` (a dead article redirected to the site root)."""
    if not url:
        return False
    return urlsplit(url).path in ("", "/") and not urlsplit(url).query


def best_url(entry: Mapping[str, Any]) -> str | None:
    """Most informative resolved URL for a ``link_map`` entry.

    Prefers the final URL, but falls back to the originally shared URL when the final one is a bare
    homepage (2017 support articles that now redirect to ``open.spotify.com/``).
    """
    final = entry.get("url")
    original = entry.get("original_url")
    if final and is_homepage(final) and original and original != final and not _is_shortener(original):
        return original
    return final or original


def _read_prefix(response: Any) -> bytes:
    buf = bytearray()
    for chunk in response.iter_content(chunk_size=8192):
        buf.extend(chunk)
        if len(buf) >= MAX_HTML_BYTES:
            break
    return bytes(buf[:MAX_HTML_BYTES])


def http_fetch(url: str, timeout: float = DEFAULT_TIMEOUT) -> LinkResolution:
    """Follow ``url`` with HEAD, falling back to GET, and read a title when the target is HTML.

    Never raises: network or parsing failures are reported through ``LinkResolution.error``.
    """
    import requests  # local import keeps the network client out of the offline code path

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"}
    try:
        with requests.Session() as session:
            session.headers.update(headers)
            response = session.head(url, allow_redirects=True, timeout=timeout)
            needs_get = response.status_code >= 400 or _is_html(response)
            if not needs_get:
                chain = _redirect_chain(response)
                return LinkResolution(
                    url=response.url,
                    title=None,
                    status=response.status_code,
                    original_url=_original_url(chain),
                    chain=chain,
                )
            response.close()
            with session.get(url, allow_redirects=True, timeout=timeout, stream=True) as get_response:
                title = extract_title(_read_prefix(get_response)) if _is_html(get_response) else None
                chain = _redirect_chain(get_response)
                return LinkResolution(
                    url=get_response.url,
                    title=title,
                    status=get_response.status_code,
                    original_url=_original_url(chain),
                    chain=chain,
                )
    except Exception as exc:  # noqa: BLE001 - every failure must be recorded, not raised
        return LinkResolution(url=None, title=None, status=None, error=f"{type(exc).__name__}: {exc}")


def _fetch_all(
    urls: Sequence[str], fetcher: Fetcher, workers: int, progress: Callable[[str], None] | None
) -> dict[str, LinkResolution]:
    results: dict[str, LinkResolution] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for url, res in zip(urls, pool.map(fetcher, urls), strict=True):
            results[url] = res
            if progress:
                progress(url)
    return results


def resolve_links(
    counts: Mapping[str, int],
    *,
    top_n: int = DEFAULT_TOP_N,
    workers: int = DEFAULT_WORKERS,
    timeout: float = DEFAULT_TIMEOUT,
    fetch: Fetcher | None = None,
    progress: Callable[[str], None] | None = None,
    retries: int = 1,
) -> dict[str, dict[str, Any]]:
    """Resolve the ``top_n`` most frequent links in parallel, retrying failures with fewer workers.

    Returns the ``link_map.json`` structure:
    ``{t_co_url: {"url", "original_url", "chain", "title", "count", "status", "error"}}``.
    A failed resolution keeps ``"url": None`` so callers can still see the count. Output is ordered
    by descending count and the key order is stable across runs.
    """
    fetcher: Fetcher = fetch or (lambda u: http_fetch(u, timeout=timeout))
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    urls = [u for u, _ in ranked]
    t0 = time.perf_counter()
    results = _fetch_all(urls, fetcher, workers, progress)
    for attempt in range(retries):
        failed = [u for u in urls if results[u].error]
        if not failed:
            break
        log.info(
            "retry %d: %d links failed, retrying with %d workers", attempt + 1, len(failed), RETRY_WORKERS
        )
        results.update(_fetch_all(failed, fetcher, RETRY_WORKERS, None))
    link_map = {
        url: {
            "url": res.url,
            "original_url": res.original_url,
            "chain": list(res.chain),
            "title": res.title,
            "count": int(count),
            "status": res.status,
            "error": res.error,
        }
        for (url, count), res in ((kv, results[kv[0]]) for kv in ranked)
    }
    ok = sum(1 for v in link_map.values() if v["url"])
    log.info("resolved %d/%d links (%.1fs)", ok, len(link_map), time.perf_counter() - t0)
    return link_map


def success_rate(link_map: Mapping[str, Mapping[str, Any]]) -> float:
    """Share of links in ``link_map`` that resolved to a final URL (0.0 when empty)."""
    if not link_map:
        return 0.0
    return sum(1 for v in link_map.values() if v.get("url")) / len(link_map)


def homepage_rate(link_map: Mapping[str, Mapping[str, Any]]) -> float:
    """Share of resolved links whose final URL is a bare homepage (article gone), 0.0 when none resolved."""
    resolved = [v for v in link_map.values() if v.get("url")]
    if not resolved:
        return 0.0
    return sum(1 for v in resolved if is_homepage(v["url"])) / len(resolved)


__all__ = [
    "DEFAULT_TIMEOUT",
    "DEFAULT_TOP_N",
    "DEFAULT_WORKERS",
    "LinkResolution",
    "MAX_HTML_BYTES",
    "RETRY_WORKERS",
    "USER_AGENT",
    "best_url",
    "collect_links",
    "extract_title",
    "homepage_rate",
    "http_fetch",
    "is_homepage",
    "resolve_links",
    "success_rate",
]
