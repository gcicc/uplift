"""One HTTP helper so every call carries the same User-Agent, timeout and retry policy."""

from __future__ import annotations

import time

import requests

USER_AGENT = "uplift/0.1 (+https://github.com/gcicc/uplift)"
TIMEOUT = 60


def get(
    url: str,
    *,
    params: dict | None = None,
    retries: int = 2,
    user_agent: str = USER_AGENT,
) -> requests.Response:
    """GET with a contact User-Agent; retry 429 and 5xx with backoff, raise otherwise."""
    delay = 5.0
    for attempt in range(retries + 1):
        resp = requests.get(
            url, params=params, headers={"User-Agent": user_agent}, timeout=TIMEOUT
        )
        retryable = resp.status_code == 429 or resp.status_code >= 500
        if not retryable or attempt == retries:
            resp.raise_for_status()
            return resp
        time.sleep(delay)
        delay *= 3
    raise RuntimeError("unreachable")
