"""A polite HTTP client: per-host rate limiting, retries with backoff and a file cache.

Every scraper goes through :class:`PoliteClient`, so the scraping rules live in one place:

* never more than ``rate_limits_per_min[source]`` requests per minute per source;
* cached responses are reused (forever for immutable resources, with a TTL otherwise);
* transient failures are retried with exponential backoff, then raised as
  :class:`SourceError` so the pipeline can keep the last good data and fail loudly.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import requests

from pitchiq.config import ScrapingSettings

log = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class SourceError(RuntimeError):
    """A data source could not be fetched after all retries."""

    def __init__(self, source: str, url: str, reason: str) -> None:
        """Build an error that names the source and URL."""
        super().__init__(f"[{source}] {url}: {reason}")
        self.source = source
        self.url = url


@dataclass
class _RateLimiter:
    """Minimum-interval limiter (one token bucket of size 1)."""

    min_interval_s: float
    _last: float = field(default=0.0)

    def wait(self, sleep: Callable[[float], None], now: Callable[[], float]) -> None:
        elapsed = now() - self._last
        if elapsed < self.min_interval_s:
            sleep(self.min_interval_s - elapsed)
        self._last = now()


class PoliteClient:
    """HTTP GET with caching, rate limiting and retries, scoped to one source."""

    def __init__(
        self,
        source: str,
        settings: ScrapingSettings,
        cache_dir: Path,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a client for ``source`` (a key of ``rate_limits_per_min``)."""
        if source not in settings.rate_limits_per_min:
            raise KeyError(f"no rate limit configured for source {source!r}")
        self.source = source
        self.settings = settings
        self.cache_dir = cache_dir
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", settings.user_agent)
        self._sleep = sleep
        self._now = now
        self._limiter = _RateLimiter(60.0 / settings.rate_limits_per_min[source])
        self.n_requests = 0

    def cache_path(self, url: str, suffix: str = "") -> Path:
        """Return the cache file used for ``url``."""
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / self.source / f"{digest}{suffix}"

    def get(
        self,
        url: str,
        *,
        max_age_s: float | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
        suffix: str = "",
    ) -> bytes:
        """Return the body of ``url``, from cache when fresh enough.

        Args:
            url: The URL to fetch.
            max_age_s: Maximum cache age in seconds. ``None`` means cached forever
                (use for immutable resources such as finished matches).
            headers: Extra request headers.
            use_cache: Set ``False`` to bypass and not write the cache.
            suffix: File suffix for the cache file (cosmetic, e.g. ``.json``).

        """
        path = self.cache_path(url, suffix)
        if use_cache and self._is_fresh(path, max_age_s):
            return path.read_bytes()
        body = self._fetch(url, headers or {})
        if use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(body)
            tmp.replace(path)
        return body

    def _is_fresh(self, path: Path, max_age_s: float | None) -> bool:
        if not path.exists():
            return False
        if max_age_s is None:
            return True
        return (time.time() - path.stat().st_mtime) <= max_age_s

    def _fetch(self, url: str, headers: dict[str, str]) -> bytes:
        last_reason = "unknown error"
        for attempt in range(self.settings.max_retries + 1):
            self._limiter.wait(self._sleep, self._now)
            self.n_requests += 1
            try:
                resp = self.session.get(url, headers=headers, timeout=self.settings.timeout_s)
            except requests.RequestException as exc:
                last_reason = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 200:
                    return resp.content
                last_reason = f"HTTP {resp.status_code}"
                if resp.status_code not in RETRYABLE_STATUS:
                    break
            if attempt < self.settings.max_retries:
                delay = self.settings.backoff_seconds * (2**attempt)
                log.warning(
                    "%s: %s (retry %d in %.0fs)", self.source, last_reason, attempt + 1, delay
                )
                self._sleep(delay)
        raise SourceError(self.source, url, last_reason)
