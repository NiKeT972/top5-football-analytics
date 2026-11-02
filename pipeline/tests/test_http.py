import pytest
import requests
import responses

from pitchiq.config import load_settings
from pitchiq.http import PoliteClient, SourceError


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


@responses.activate
def test_rate_limit_and_cache(tmp_path):
    responses.get("https://x.test/a", body=b"A")
    responses.get("https://x.test/b", body=b"B")
    clock = Clock()
    c = PoliteClient(
        "fbref", load_settings().scraping, tmp_path, requests.Session(), clock.sleep, clock.now
    )
    clock.t = 100.0
    assert c.get("https://x.test/a") == b"A"
    assert c.get("https://x.test/b") == b"B"
    # 10 requests/min -> at least 6 s between requests
    assert clock.slept and abs(clock.slept[-1] - 6.0) < 1e-6
    assert c.get("https://x.test/a") == b"A"  # served from cache
    assert c.n_requests == 2


@responses.activate
def test_retries_then_source_error(tmp_path):
    responses.get("https://x.test/fail", status=503)
    clock = Clock()
    c = PoliteClient(
        "understat", load_settings().scraping, tmp_path, requests.Session(), clock.sleep, clock.now
    )
    with pytest.raises(SourceError):
        c.get("https://x.test/fail")
    assert c.n_requests == load_settings().scraping.max_retries + 1


@responses.activate
def test_non_retryable_status_fails_fast(tmp_path):
    responses.get("https://x.test/404", status=404)
    clock = Clock()
    c = PoliteClient(
        "understat", load_settings().scraping, tmp_path, requests.Session(), clock.sleep, clock.now
    )
    with pytest.raises(SourceError, match="HTTP 404"):
        c.get("https://x.test/404")
    assert c.n_requests == 1
