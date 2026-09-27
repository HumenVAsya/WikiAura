"""Unit tests for the Wikimedia exponential backoff retry module."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from app.services.wikimedia.retry import (
    RETRYABLE_STATUS_CODES,
    WikimediaRateLimitError,
    WikimediaServerError,
    get_with_retry,
    with_retry,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _mock_response(status: int, body: str = "{}", headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, content=body.encode(), headers=headers or {})


def _make_fn(responses: list[httpx.Response]):
    """Create an async callable that returns each response in sequence."""
    iter_ = iter(responses)

    async def fn() -> httpx.Response:
        return next(iter_)

    return fn


# ── with_retry: Success path ───────────────────────────────────────────────────


class TestWithRetrySuccess:
    @pytest.mark.asyncio
    async def test_immediate_success_no_delay(self):
        """A 200 on the first attempt should return immediately."""
        fn = _make_fn([_mock_response(200)])
        resp = await with_retry(fn, max_attempts=3, base_delay=0.0)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_success_after_one_retry(self):
        """429 on attempt 1, then 200 on attempt 2."""
        fn = _make_fn([
            _mock_response(429),
            _mock_response(200),
        ])
        resp = await with_retry(fn, max_attempts=3, base_delay=0.0, jitter=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_success_after_two_retries(self):
        """503 on attempts 1-2, then 200 on attempt 3."""
        fn = _make_fn([
            _mock_response(503),
            _mock_response(503),
            _mock_response(200),
        ])
        resp = await with_retry(fn, max_attempts=3, base_delay=0.0, jitter=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_non_retryable_404_returned_immediately(self):
        """404 is NOT retryable — should be returned as-is on first attempt."""
        fn = _make_fn([_mock_response(404)])
        resp = await with_retry(fn, max_attempts=5, base_delay=0.0)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_non_retryable_400_returned_immediately(self):
        """400 is NOT retryable — should be returned immediately."""
        fn = _make_fn([_mock_response(400)])
        resp = await with_retry(fn, max_attempts=5, base_delay=0.0)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_all_retryable_codes_trigger_retry(self):
        """Every code in RETRYABLE_STATUS_CODES must trigger a retry."""
        for code in RETRYABLE_STATUS_CODES:
            fn = _make_fn([_mock_response(code), _mock_response(200)])
            resp = await with_retry(fn, max_attempts=2, base_delay=0.0, jitter=False)
            assert resp.status_code == 200, f"Code {code} should trigger retry"


# ── with_retry: Failure / exhaustion path ─────────────────────────────────────


class TestWithRetryExhaustion:
    @pytest.mark.asyncio
    async def test_raises_rate_limit_error_after_all_429(self):
        """All attempts return 429 → WikimediaRateLimitError."""
        fn = _make_fn([_mock_response(429)] * 3)
        with pytest.raises(WikimediaRateLimitError) as exc_info:
            await with_retry(fn, max_attempts=3, base_delay=0.0, jitter=False)
        assert exc_info.value.last_status_code == 429
        assert exc_info.value.attempts == 3

    @pytest.mark.asyncio
    async def test_raises_server_error_after_all_503(self):
        """All attempts return 503 → WikimediaServerError."""
        fn = _make_fn([_mock_response(503)] * 3)
        with pytest.raises(WikimediaServerError) as exc_info:
            await with_retry(fn, max_attempts=3, base_delay=0.0, jitter=False)
        assert exc_info.value.last_status_code == 503

    @pytest.mark.asyncio
    async def test_raises_server_error_for_500(self):
        fn = _make_fn([_mock_response(500)] * 2)
        with pytest.raises(WikimediaServerError):
            await with_retry(fn, max_attempts=2, base_delay=0.0, jitter=False)

    @pytest.mark.asyncio
    async def test_raises_server_error_for_502(self):
        fn = _make_fn([_mock_response(502)] * 2)
        with pytest.raises(WikimediaServerError):
            await with_retry(fn, max_attempts=2, base_delay=0.0, jitter=False)

    @pytest.mark.asyncio
    async def test_raises_server_error_for_504(self):
        fn = _make_fn([_mock_response(504)] * 2)
        with pytest.raises(WikimediaServerError):
            await with_retry(fn, max_attempts=2, base_delay=0.0, jitter=False)

    @pytest.mark.asyncio
    async def test_network_error_not_retried(self):
        """httpx.ConnectError (network failure) must propagate immediately."""
        async def failing_fn():
            raise httpx.ConnectError("Network unreachable")

        with pytest.raises(httpx.ConnectError):
            await with_retry(failing_fn, max_attempts=3, base_delay=0.0)

    @pytest.mark.asyncio
    async def test_max_attempts_1_no_retry(self):
        """With max_attempts=1, a single 503 should raise immediately."""
        fn = _make_fn([_mock_response(503)])
        with pytest.raises(WikimediaServerError) as exc_info:
            await with_retry(fn, max_attempts=1, base_delay=0.0, jitter=False)
        assert exc_info.value.attempts == 1


# ── with_retry: Retry-After header ────────────────────────────────────────────


class TestRetryAfterHeader:
    @pytest.mark.asyncio
    async def test_retry_after_header_respected(self):
        """429 with Retry-After: 0.05 should wait ~50ms before retry."""
        fn = _make_fn([
            _mock_response(429, headers={"Retry-After": "0.05"}),
            _mock_response(200),
        ])
        t0 = time.monotonic()
        resp = await with_retry(fn, max_attempts=2, base_delay=0.0, jitter=False)
        elapsed = time.monotonic() - t0
        assert resp.status_code == 200
        assert elapsed >= 0.04, f"Expected ~50ms delay, got {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_invalid_retry_after_uses_exponential(self):
        """Malformed Retry-After header should fall back to exponential delay."""
        fn = _make_fn([
            _mock_response(429, headers={"Retry-After": "not-a-number"}),
            _mock_response(200),
        ])
        resp = await with_retry(fn, max_attempts=2, base_delay=0.0, jitter=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_max_delay_cap_applied(self):
        """Delay should never exceed max_delay even with large Retry-After."""
        fn = _make_fn([
            _mock_response(429, headers={"Retry-After": "9999"}),
            _mock_response(200),
        ])
        # max_delay=0.01 → even if server says 9999s, we cap at 0.01s
        t0 = time.monotonic()
        resp = await with_retry(fn, max_attempts=2, base_delay=0.0, max_delay=0.01, jitter=False)
        elapsed = time.monotonic() - t0
        assert resp.status_code == 200
        assert elapsed < 1.0, f"Should respect max_delay, got {elapsed:.3f}s"


# ── with_retry: Jitter ────────────────────────────────────────────────────────


class TestJitter:
    @pytest.mark.asyncio
    async def test_jitter_enabled_by_default(self):
        """Default behaviour includes jitter — should still eventually succeed."""
        fn = _make_fn([_mock_response(503), _mock_response(200)])
        resp = await with_retry(fn, max_attempts=2, base_delay=0.0)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_jitter_disabled_works(self):
        """jitter=False should produce deterministic delays without error."""
        fn = _make_fn([_mock_response(503), _mock_response(200)])
        resp = await with_retry(fn, max_attempts=2, base_delay=0.0, jitter=False)
        assert resp.status_code == 200


# ── get_with_retry: Convenience wrapper ───────────────────────────────────────


class TestGetWithRetry:
    @pytest.mark.asyncio
    @respx.mock
    async def test_success_on_first_attempt(self):
        """Single 200 response via get_with_retry."""
        respx.get("https://test.example.com/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        async with httpx.AsyncClient() as client:
            resp = await get_with_retry(
                client, "https://test.example.com/path",
                max_attempts=3, base_delay=0.0,
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    @pytest.mark.asyncio
    @respx.mock
    async def test_retry_on_429_then_success(self):
        """429 then 200 via get_with_retry."""
        route = respx.get("https://test.example.com/retry")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(200, json={"result": "ok"}),
        ]
        async with httpx.AsyncClient() as client:
            resp = await get_with_retry(
                client, "https://test.example.com/retry",
                max_attempts=2, base_delay=0.0, jitter=False,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_rate_limit_error_on_all_429(self):
        """All 429s → WikimediaRateLimitError from get_with_retry."""
        respx.get("https://test.example.com/rate").mock(return_value=httpx.Response(429))
        async with httpx.AsyncClient() as client:
            with pytest.raises(WikimediaRateLimitError):
                await get_with_retry(
                    client, "https://test.example.com/rate",
                    max_attempts=2, base_delay=0.0, jitter=False,
                )

    @pytest.mark.asyncio
    @respx.mock
    async def test_params_forwarded_correctly(self):
        """Query params passed to get_with_retry should reach the URL."""
        respx.get("https://test.example.com/api", params={"action": "query"}).mock(
            return_value=httpx.Response(200, json={})
        )
        async with httpx.AsyncClient() as client:
            resp = await get_with_retry(
                client, "https://test.example.com/api",
                params={"action": "query"},
                max_attempts=1, base_delay=0.0,
            )
        assert resp.status_code == 200


# ── Error hierarchy ────────────────────────────────────────────────────────────


class TestErrorHierarchy:
    def test_rate_limit_error_is_retry_error(self):
        from app.services.wikimedia.retry import WikimediaRetryError
        err = WikimediaRateLimitError("test", last_status_code=429, attempts=3)
        assert isinstance(err, WikimediaRetryError)
        assert err.last_status_code == 429
        assert err.attempts == 3

    def test_server_error_is_retry_error(self):
        from app.services.wikimedia.retry import WikimediaRetryError
        err = WikimediaServerError("test", last_status_code=503, attempts=2)
        assert isinstance(err, WikimediaRetryError)
        assert err.last_status_code == 503

    def test_error_message_included(self):
        err = WikimediaRateLimitError("All 3 attempts failed", last_status_code=429, attempts=3)
        assert "3 attempts" in str(err)
