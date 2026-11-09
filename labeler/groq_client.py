"""Minimal Groq chat-completions client (OpenAI-compatible REST) using only the standard library.

Reliability features: per-request timeout, exponential backoff with jitter, honours
Retry-After / rate-limit reset headers on 429, retries 5xx and network errors, and
proactively waits when the per-minute token budget is nearly exhausted.
"""
from __future__ import annotations

import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.groq.com/openai/v1/chat/completions"
USER_AGENT = "call-disposition-labeler/1.0"


class GroqError(RuntimeError):
    pass


def load_api_key(name: str = "GROQ_API_KEY") -> str:
    """Read the API key (default GROQ_API_KEY) from the environment; fall back to a .env file in cwd or its parents."""
    key = os.environ.get(name, "").strip()
    if key:
        return key
    for d in [Path.cwd(), *Path.cwd().parents]:
        f = d / ".env"
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip() == name:
                        return v.strip().strip('"').strip("'")
    raise GroqError(f"{name} is not set (environment variable or .env file).")


def _parse_duration(s: str | None) -> float | None:
    """Parse Groq reset durations like '6.4s', '1m26.4s', '915ms'."""
    if not s:
        return None
    total, found = 0.0, False
    for num, unit in re.findall(r"([\d.]+)(ms|h|m|s)", s):
        found = True
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return total if found else None


class GroqClient:
    def __init__(self, api_key: str, timeout: float = 120.0, max_retries: int = 6, max_daily_wait: float = 1800.0,
                 api_url: str = API_URL):
        self.api_url = api_url  # any OpenAI-compatible endpoint; Groq by default
        self.api_key, self.timeout, self.max_retries = api_key, timeout, max_retries
        self.max_daily_wait = max_daily_wait  # wait (instead of failing) when a daily quota frees up within this many seconds
        self._lock = threading.Lock()
        self._not_before = 0.0  # shared pacing gate across threads

    def _wait_gate(self):
        with self._lock:
            delay = self._not_before - time.time()
        if delay > 0:
            time.sleep(delay)

    def _push_gate(self, seconds: float):
        with self._lock:
            self._not_before = max(self._not_before, time.time() + seconds)

    def chat(self, body: dict) -> tuple[dict, dict]:
        """POST a chat completion. Returns (response_json, info) where info has retries and headers."""
        data = json.dumps(body).encode("utf-8")
        last_err = None
        for attempt in range(self.max_retries + 1):
            self._wait_gate()
            req = urllib.request.Request(self.api_url, data=data, method="POST", headers={
                "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    headers = {k.lower(): v for k, v in r.headers.items()}
                    resp = json.loads(r.read().decode("utf-8"))
                # Proactive pacing: if the minute token budget is nearly spent, wait for its reset.
                rem = headers.get("x-ratelimit-remaining-tokens")
                if rem is not None and rem.isdigit() and int(rem) < 6000:
                    self._push_gate(_parse_duration(headers.get("x-ratelimit-reset-tokens")) or 0)
                return resp, {"attempts": attempt + 1, "headers": headers}
            except urllib.error.HTTPError as e:
                payload = e.read().decode("utf-8", "replace")[:800]
                last_err = f"HTTP {e.code}: {payload}"
                if e.code == 429 or e.code >= 500:
                    hdr = {k.lower(): v for k, v in (e.headers or {}).items()}
                    wait = _parse_duration(hdr.get("retry-after") and hdr["retry-after"] + "s") \
                        or _parse_duration(hdr.get("x-ratelimit-reset-tokens")) or (2 ** attempt)
                    if "per day" in payload.lower() or "(tpd)" in payload.lower() or "(rpd)" in payload.lower():
                        m = re.search(r"try again in ([\dhms.]+)", payload)
                        daily_wait = _parse_duration(m.group(1)) if m else None
                        if daily_wait is not None and daily_wait <= self.max_daily_wait:
                            print(f"  daily limit reached; waiting {daily_wait:.0f}s as instructed by Groq", flush=True)
                            self._push_gate(daily_wait + 2)
                            continue
                        raise GroqError("Daily token limit reached: " + payload)
                    wait = min(wait + random.uniform(0.2, 1.5), 90)
                    self._push_gate(wait)
                    continue
                raise GroqError(last_err)  # 4xx other than 429: not retryable (bad request/auth)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last_err = f"network: {e}"
                time.sleep(min(2 ** attempt + random.random(), 30))
        raise GroqError(f"failed after {self.max_retries + 1} attempts: {last_err}")
