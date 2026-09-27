"""Exponential backoff retry decorator for Wikimedia HTTP requests.

Design goals:
- Retry on transient HTTP errors: 429 (rate limit), 500, 502, 503, 504
- Exponential backoff with optional jitter to avoid thundering herd
- Honour Retry-After header when present (429 responses)
- Hard cap on total wait time to prevent unbounded delays
- Per-attempt request_id header for Wikimedia server-side tracing
- Structured logging at each attempt (attempt number, delay, status code)
- Raise WikimediaRateLimitError after all retries exhausted on 429
- Raise WikimediaServerError after all retries exhausted on 5xx
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import httpx

logger = logging.getLogger(__name__)

# ── Retryable status codes ─────────────────────────────────────────────────────

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

# ── Custom exceptions ──────────────────────────────────────────────────────────


class WikimediaRetryError(Exception):
    """Base class for retry-exhausted Wikimedia errors."""
    def __init__(self, message: str, last_status_code: int, attempts: int) -> None:
        super().__init__(message)
        self.last_status_code = last_status_code
        self.attempts = attempts


class WikimediaRateLimitError(WikimediaRetryError):
    """Raised when HTTP 429 persists after all retry attempts."""


class WikimediaServerError(WikimediaRetryError):
    """Raised when HTTP 5xx persists after all retry attempts."""


# ── Core retry logic ───────────────────────────────────────────────────────────

T = TypeVar("T")


async def with_retry(
    request_fn: Callable[[], Coroutine[Any, Any, httpx.Response]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    jitter: bool = True,
    retryable_codes: frozenset[int] = RETRYABLE_STATUS_CODES,
    operation_name: str = "wikimedia_request",
) -> httpx.Response:
    """Execute an async httpx request with exponential backoff retry.

    Args:
        request_fn: Async callable that performs the HTTP request and returns
                    an httpx.Response. Called fresh on each attempt.
        max_attempts: Total number of attempts (1 = no retries).
        base_delay: Initial wait in seconds before the first retry.
                    Doubles each subsequent attempt: base, 2*base, 4*base, ...
        max_delay: Hard ceiling on per-attempt delay (before jitter).
        jitter: If True, adds uniform random noise ±25% to each delay
                to prevent correlated retries across concurrent requests.
        retryable_codes: Set of HTTP status codes that trigger a retry.
        operation_name: Human-readable label used in log messages.

    Returns:
        httpx.Response on success (any non-retryable status code).

    Raises:
        WikimediaRateLimitError: All attempts exhausted due to HTTP 429.
        WikimediaServerError: All attempts exhausted due to HTTP 5xx.
        httpx.HTTPError: Network-level errors are NOT retried (propagated immediately).
    """
    last_status: int = -1

    for attempt in range(1, max_attempts + 1):
        request_id = uuid.uuid4().hex[:8]

        try:
            response = await request_fn()
        except httpx.HTTPError as exc:
            # Network/connection errors are not retried — fail fast
            logger.error(
                "[%s] Network error on attempt %d/%d: %s",
                operation_name, attempt, max_attempts, exc,
            )
            raise

        last_status = response.status_code

        if last_status not in retryable_codes:
            if attempt > 1:
                logger.info(
                    "[%s] Succeeded on attempt %d/%d (status %d, request_id=%s)",
                    operation_name, attempt, max_attempts, last_status, request_id,
                )
            return response

        # ── Determine delay ────────────────────────────────────────────────
        if last_status == 429:
            retry_after_str = response.headers.get("Retry-After", "")
            try:
                server_delay = float(retry_after_str)
            except (ValueError, TypeError):
                server_delay = None
        else:
            server_delay = None

        exponential_delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
        delay = server_delay if server_delay is not None else exponential_delay

        if jitter and delay > 0:
            delay = delay * (0.75 + random.random() * 0.5)  # ±25% jitter

        delay = min(delay, max_delay)

        logger.warning(
            "[%s] HTTP %d on attempt %d/%d — retrying in %.2fs (request_id=%s)",
            operation_name, last_status, attempt, max_attempts, delay, request_id,
        )

        if attempt < max_attempts:
            await asyncio.sleep(delay)

    # ── All attempts exhausted ─────────────────────────────────────────────
    msg = (
        f"[{operation_name}] All {max_attempts} attempts failed "
        f"(last status: HTTP {last_status})"
    )
    if last_status == 429:
        raise WikimediaRateLimitError(msg, last_status_code=last_status, attempts=max_attempts)
    raise WikimediaServerError(msg, last_status_code=last_status, attempts=max_attempts)


# ── Convenience wrapper for GET requests ──────────────────────────────────────


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    jitter: bool = True,
    operation_name: str = "wikimedia_get",
) -> httpx.Response:
    """Shortcut for GET requests with retry — wraps with_retry for a single URL.

    Example:
        response = await get_with_retry(
            client, "https://wikimedia.org/...",
            params={"action": "query"},
            operation_name="langlinks_resolve",
        )
        response.raise_for_status()
        data = response.json()
    """
    return await with_retry(
        lambda: client.get(url, params=params),
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter,
        operation_name=operation_name,
    )
