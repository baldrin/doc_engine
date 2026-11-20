"""The model gateway: one client, one function that makes a call and classifies what came back.

max_retries is 0 so that every rejection is seen by the scheduler instead of being retried
silently inside the SDK. The bearer token is resolved for every request.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import anthropic
import httpx2
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

from .config import Section, gateway_token

log = logging.getLogger("doc_engine.gateway")

TRANSIENT_STATUS = {408, 409, 500, 502, 503, 504, 529}


def make_client(cfg: Section) -> AsyncAnthropic:
    max_conn = int(cfg.gateway.get("max_connections", 512))
    timeout = float(cfg.gateway.get("request_timeout_s", 600))
    limits = httpx2.Limits(max_connections=max_conn, max_keepalive_connections=max_conn, keepalive_expiry=30.0)
    http_client = DefaultAsyncHttpxClient(limits=limits, timeout=httpx2.Timeout(timeout, connect=30.0))
    client = AsyncAnthropic(
        base_url=cfg.gateway.base_url,
        auth_token="resolved-per-request",  # replaced on every request by auth_headers()
        max_retries=0,
        timeout=timeout,
        http_client=http_client,
    )
    log.info("gateway client: base_url=%s max_retries=0 timeout=%ss http max_connections=%d",
             cfg.gateway.base_url, timeout, max_conn)
    return client


def auth_headers(cfg: Section) -> dict[str, str]:
    return {"Authorization": f"Bearer {gateway_token(cfg)}"}


@dataclass
class CallResult:
    outcome: str = "ok"            # ok | 429 | transient | permanent | refusal | empty
    http_status: int | None = None
    sent_at: datetime | None = None
    first_token_at: datetime | None = None
    done_at: datetime | None = None
    duration_s: float = 0.0
    text: str = ""
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    request_id: str | None = None
    limit_type: str | None = None
    request_bytes: int | None = None
    error: dict[str, Any] | None = None
    block_types: list[str] = field(default_factory=list)

    @property
    def counted_input(self) -> int:
        """What counts against the input limit: cache reads are free (probe 8), cache writes are not."""
        return self.input_tokens + self.cache_write

    @property
    def truncated(self) -> bool:
        return self.stop_reason in ("max_tokens", "model_context_window_exceeded")


def parse_429(body: Any, text: str) -> str:
    """The limit a rejection names. The gateway's body is only
    {"error_code": "REQUEST_LIMIT_EXCEEDED", "message": "... Exceeded workspace output tokens per minute rate limit ..."}
    with no limit, current or retry timing, so the message text is all there is."""
    msg = ""
    if isinstance(body, dict):
        err = body.get("error")
        msg = str(body.get("message") or (err.get("message") if isinstance(err, dict) else "") or body)
    msg = msg or text or ""
    m = re.search(r"(output|input) tokens per minute|queries per hour|requests per second", msg, re.I)
    if m:
        s = m.group(0).lower()
        return "output" if s.startswith("output") else "input" if s.startswith("input") else "queries"
    if re.search(r"output", msg, re.I):
        return "output"
    if re.search(r"input", msg, re.I):
        return "input"
    return "unknown"


# Error types a gateway can send inside a stream that has already answered 200.
STREAM_TRANSIENT = {"overloaded_error", "api_error", "timeout_error"}


def _error_type(body: Any) -> str:
    """The error type named in an error body, or '' when there is none."""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("type") or "")
        return str(body.get("type") or "")
    return ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _usage(res: CallResult, usage: Any) -> None:
    if usage is None:
        return
    res.input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    res.output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    res.cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    res.cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)


def _finish(res: CallResult, msg: Any, is_warmup: bool) -> None:
    res.stop_reason = getattr(msg, "stop_reason", None)
    _usage(res, getattr(msg, "usage", None))
    texts = []
    for b in getattr(msg, "content", None) or []:
        res.block_types.append(getattr(b, "type", "?"))
        if getattr(b, "type", None) == "text":
            texts.append(b.text or "")
    res.text = "".join(texts)
    if res.stop_reason == "refusal":
        res.outcome = "refusal"
        det = getattr(msg, "stop_details", None)
        res.error = {"message": getattr(det, "explanation", None) or "",
                     "category": getattr(det, "category", None), "explanation": getattr(det, "explanation", None)}
    elif not is_warmup and not res.text.strip():
        # e.g. thinking used the whole max_tokens. A reply with no text must not pass as a success.
        res.outcome = "empty"
        res.error = {"message": f"the reply held no text (stop_reason {res.stop_reason}, blocks {res.block_types})"}


async def execute_call(client: AsyncAnthropic, cfg: Section, params: dict, *, streaming: bool = False,
                       is_warmup: bool = False,
                       on_progress: Callable[[int], Awaitable[None]] | None = None) -> CallResult:
    """Makes one model call. Never raises for an API outcome; the result says what happened."""
    res = CallResult()
    t0 = time.monotonic()
    res.sent_at = _now()
    try:
        try:
            headers = auth_headers(cfg)
        except Exception as e:
            # No token says nothing about the call itself. It is tried again, like a gateway error.
            res.outcome = "transient"
            res.error = {"message": f"could not get a gateway token: {type(e).__name__}: {e}"[:2000]}
            res.done_at = _now()
            res.duration_s = time.monotonic() - t0
            return res
        if streaming:
            chars = 0
            last_report = 0.0
            async with client.messages.stream(**params, extra_headers=headers) as stream:
                res.http_status = stream.response.status_code
                res.request_id = stream.response.headers.get("x-request-id")
                async for ev in stream:
                    if ev.type == "content_block_delta":
                        if res.first_token_at is None:
                            res.first_token_at = _now()
                        d = ev.delta
                        chars += len(getattr(d, "text", "") or getattr(d, "thinking", "") or "")
                        now = time.monotonic()
                        if on_progress is not None and now - last_report >= 1.0:
                            last_report = now
                            await on_progress(int(chars / 3.6))
                msg = await stream.get_final_message()
            if getattr(msg, "stop_reason", None) is None:
                # The stream closed before the reply said how it ended: part of a reply, not a reply.
                res.outcome = "transient"
                res.error = {"message": "the streamed reply ended before it was complete"}
                res.done_at = _now()
                res.duration_s = time.monotonic() - t0
                return res
        else:
            raw = await client.messages.with_raw_response.create(**params, extra_headers=headers)
            res.http_status = raw.status_code
            res.request_id = raw.headers.get("x-request-id")
            msg = await raw.parse()
        _finish(res, msg, is_warmup)
    except anthropic.RateLimitError as e:
        res.outcome = "429"
        res.http_status = 429
        body = getattr(e, "body", None)
        text = ""
        try:
            text = e.response.text
            res.request_id = e.response.headers.get("x-request-id")
        except Exception:
            pass
        res.limit_type = parse_429(body, text)
        res.error = {"body": body if isinstance(body, (dict, list, str)) else str(body), "text": text[:2000]}
    except anthropic.APIStatusError as e:
        res.http_status = e.status_code
        body = getattr(e, "body", None)
        kind = _error_type(body)
        if e.status_code in TRANSIENT_STATUS:
            res.outcome = "transient"
        elif e.status_code == 200 and kind == "rate_limit_error":
            # An error event inside a stream carries the stream's own status, 200.
            res.outcome = "429"
            res.limit_type = parse_429(body, str(e))
        elif e.status_code == 200 and kind in STREAM_TRANSIENT:
            res.outcome = "transient"
        else:
            res.outcome = "permanent"
        res.error = {"body": body if isinstance(body, (dict, list, str)) else str(body), "message": str(e)[:2000]}
        try:
            res.request_id = e.response.headers.get("x-request-id")
        except Exception:
            pass
    except (anthropic.APITimeoutError, anthropic.APIConnectionError, httpx2.TransportError) as e:
        # httpx2.TransportError: a connection lost while a streamed reply was being read, which the
        # SDK passes on as it is.
        res.outcome = "transient"
        res.error = {"message": f"{type(e).__name__}: {e}"[:2000]}
    except asyncio.CancelledError:
        raise
    except Exception as e:  # anything unexpected is recorded, not swallowed
        res.outcome = "permanent"
        res.error = {"message": f"{type(e).__name__}: {e}"[:2000]}
        log.exception("unexpected error during a model call")
    res.done_at = _now()
    res.duration_s = time.monotonic() - t0
    return res


def call_cost(cfg: Section, model: str, res: CallResult) -> float:
    p = cfg.models[model].pricing
    return (res.input_tokens * p.input + res.output_tokens * p.output
            + res.cache_read * p.cache_read + res.cache_write * p.cache_write) / 1e6
