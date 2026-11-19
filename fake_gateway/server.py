"""A stand-in for the Databricks AI Gateway, for testing the engine without the workspace.

It imitates what was MEASURED on the real gateway on 2026-11-14 to 16, not the documentation:
  - nothing is reserved at admission; actual output is charged when a call completes
  - output is a token bucket (about 40K) refilling at OTPM/60 per second; requests are admitted
    blindly while the bucket is not empty, then rejected until the debt clears
  - a 429 returns in about 0.3 s with only {"error_code", "message"}: no limit, no retry timing, no header
  - cache reads do not count against the input limit; cache writes do
  - a cache entry is readable only after the call that wrote it has started answering
  - models think by default; Sonnet and Opus reject {"type": "disabled"}; only Sonnet takes "between_tools"
  - a body over about 20 MB gets a misleading "malformed JSON" 400

Nothing learned from this server says anything about the real gateway. It only shows the code runs.

  python -m fake_gateway --port 8765 --speed 10
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import time
import uuid
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

LOREM = ("The record documents a follow up visit and notes stable findings since the prior encounter. "
         "Medication was reviewed and continued without change. The reviewer recorded no new complaints. "
         "Laboratory values were within the reference range except where flagged. A further review was scheduled. "
         "The section lists the parties, the effective date and the obligations that follow from them. "
         "Payment terms and the renewal conditions are stated without amendment. ").split(". ")


class Bucket:
    def __init__(self, capacity: float, per_minute: float) -> None:
        self.capacity = capacity
        self.rate = per_minute / 60.0
        self.tokens = capacity
        self.t = time.monotonic()

    def refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.t) * self.rate)
        self.t = now

    def empty(self) -> bool:
        self.refill()
        return self.tokens <= 0

    def take(self, n: float) -> None:
        self.refill()
        self.tokens -= n


class State:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.out: dict[str, Bucket] = {}
        self.inp: dict[str, Bucket] = {}
        self.cache: dict[str, tuple[float, float]] = {}   # hash -> (readable_at, expires_at)
        self.stats: dict[str, Any] = {"requests": 0, "ok": 0, "429_output": 0, "429_input": 0, "400": 0,
                                      "output_tokens": 0, "cache_reads": 0, "cache_writes": 0, "in_flight": 0,
                                      "peak_in_flight": 0}

    def buckets(self, model: str) -> tuple[Bucket, Bucket]:
        if model not in self.out:
            self.out[model] = Bucket(self.args.bucket, self.args.otpm)
            self.inp[model] = Bucket(self.args.itpm, self.args.itpm)
        return self.out[model], self.inp[model]


def tokens_of(text: str) -> int:
    return max(1, int(len(text) / 3.6))


def count_pages(b64: str) -> int:
    import base64
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return 1
    return max(1, len(re.findall(rb"/Type\s*/Page(?![s\w])", raw)))


def measure(body: dict, per_page: int) -> dict:
    """Token counts for a request: the cacheable prefix, and what follows it."""
    system = body.get("system") or []
    if isinstance(system, str):
        system = [{"type": "text", "text": system}]
    prefix_text, prefix_tokens, rest_tokens, marked = "", 0, 0, False
    last_mark = max((i for i, b in enumerate(system) if b.get("cache_control")), default=-1)
    for i, b in enumerate(system):
        t = tokens_of(b.get("text", ""))
        if i <= last_mark:
            prefix_text += b.get("text", "")
            prefix_tokens += t
            marked = True
        else:
            rest_tokens += t
    pages, user_text = 0, ""
    for m in body.get("messages", []):
        c = m.get("content")
        if isinstance(c, str):
            rest_tokens += tokens_of(c)
            user_text += c
            continue
        for b in c or []:
            if b.get("type") == "text":
                rest_tokens += tokens_of(b.get("text", ""))
                user_text += b.get("text", "") + "\n"
            elif b.get("type") == "document":
                n = count_pages((b.get("source") or {}).get("data", ""))
                pages += n
                rest_tokens += n * per_page
            elif b.get("type") == "image":
                pages += 1
                rest_tokens += per_page
    return {"prefix_text": prefix_text, "prefix_tokens": prefix_tokens, "rest_tokens": rest_tokens,
            "marked": marked, "pages": pages, "user_text": user_text,
            "system_text": "".join(b.get("text", "") for b in system)}


def fake_value(schema: dict, rng: random.Random, name: str = "") -> Any:
    t = schema.get("type")
    if "enum" in schema:
        vals = schema["enum"]
        # make one value rare, so a filter keeps a small share of the pages
        weights = [1 if re.search(r"lab|invoice|amend", str(v), re.I) else 6 for v in vals]
        return rng.choices(vals, weights=weights)[0]
    if t == "object":
        return {k: fake_value(v, rng, k) for k, v in (schema.get("properties") or {}).items()}
    if t == "array":
        item = schema.get("items") or {"type": "string"}
        return [fake_value(item, rng, name) for _ in range(rng.randint(2, 7))]
    if t == "number":
        return round(rng.uniform(1, 200), 1)
    if t == "boolean":
        return rng.random() < 0.3
    if isinstance(t, list):
        if re.search(r"value|amount|result", name, re.I):
            return round(rng.uniform(1, 200), 1)
        return rng.choice(["Hemoglobin", "Sodium", "Creatinine", "Glucose", "mg/dL", "mmol/L", "normal", "high", "low"])
    return rng.choice(LOREM)[:60]


def pages_from(user_text: str) -> list[int]:
    m = re.search(r"pages? ([\d, \-]+) of", user_text)
    if not m:
        return []
    out: list[int] = []
    for part in m.group(1).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            if a.strip().isdigit() and b.strip().isdigit():
                out.extend(range(int(a), int(b) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out[:400]


def make_reply(body: dict, info: dict, rng: random.Random) -> tuple[str, int, int]:
    """(text, thinking_tokens, target_output_tokens)"""
    max_tokens = int(body.get("max_tokens", 1024))
    thinking = body.get("thinking")
    effort = (body.get("output_config") or {}).get("effort")
    think = 0
    if thinking is None:
        think = int(rng.uniform(300, 900))                       # thinks by default
    elif thinking.get("type") == "adaptive":
        think = {"low": int(rng.random() < 0.3) * 200, "medium": int(rng.random() < 0.5) * 400,
                 "high": int(rng.uniform(250, 900))}.get(effort or "high", 300)
    sysx = info["system_text"]
    if "JSON Schema exactly:" in sysx:
        try:
            schema = json.loads(sysx.split("JSON Schema exactly:", 1)[1].strip().split("\n\n")[0])
            text = json.dumps(fake_value(schema, rng))
        except Exception:
            text = "{}"
        return text, think, tokens_of(text)
    pages = pages_from(info["user_text"]) or [1]
    named = re.search(r'of the input named "([^"]+)"', info["user_text"])     # flows with several sources
    cite = f"{named.group(1)} p." if named else "p."
    n_items = info["user_text"].count("<item ")
    share = rng.uniform(0.45, 0.75) if n_items < 2 else rng.uniform(0.3, 0.7)
    target = max(1, int(max_tokens * share)) if max_tokens > 8 else max_tokens
    parts: list[str] = []
    size = 0
    heading = 0
    while size < target * 3.6:
        if heading % 6 == 0 and max_tokens > 200:
            parts.append(f"\n\n## Finding group {heading // 6 + 1}\n")
        s = rng.choice(LOREM).strip()
        p = rng.choice(pages)
        s = f"{s} [{cite} {p}]." if rng.random() < 0.6 else s + "."
        parts.append(s + " ")
        size += len(s) + 1
        heading += 1
    return "".join(parts).strip(), think, target


def build_app(args: argparse.Namespace) -> FastAPI:
    st = State(args)
    app = FastAPI()
    speed = max(0.01, args.speed)

    @app.get("/stats")
    async def stats() -> dict:
        return {**st.stats, "buckets": {m: round(b.tokens) for m, b in st.out.items()}}

    @app.post("/reset")
    async def reset() -> dict:
        st.out.clear()
        st.inp.clear()
        st.cache.clear()
        for k in st.stats:
            st.stats[k] = 0
        return {"ok": True}

    @app.post("/v1/messages")
    async def messages(request: Request):
        raw = await request.body()
        st.stats["requests"] += 1
        rid = uuid.uuid4().hex
        hdr = {"x-request-id": rid}
        if len(raw) > args.max_body_mb * 1024 * 1024:
            st.stats["400"] += 1
            return JSONResponse({"error_code": "BAD_REQUEST", "message": "The JSON object in the request body is malformed"},
                                status_code=400, headers=hdr)
        body = json.loads(raw)
        model = body.get("model", "")
        short = model.rsplit(".", 1)[-1]
        thinking = body.get("thinking")
        ttype = (thinking or {}).get("type")
        if ttype == "disabled" and ("sonnet" in model or "opus" in model):
            st.stats["400"] += 1
            hint = ' Use {"type": "between_tools"} to turn thinking off.' if "sonnet" in model else ""
            return JSONResponse({"error_code": "BAD_REQUEST",
                                 "message": f'thinking.type "disabled" is not supported for this model.{hint}'},
                                status_code=400, headers=hdr)
        if ttype == "between_tools" and "sonnet" not in model:
            st.stats["400"] += 1
            return JSONResponse({"error_code": "BAD_REQUEST",
                                 "message": 'thinking.type "between_tools" is not supported for this model.'},
                                status_code=400, headers=hdr)

        info = measure(body, args.tokens_per_page)
        out_b, in_b = st.buckets(model)
        now = time.monotonic()
        key = hashlib.sha256((model + info["prefix_text"]).encode()).hexdigest()
        cacheable = info["marked"] and info["prefix_tokens"] >= args.cache_min_tokens
        entry = st.cache.get(key) if cacheable else None
        hit = entry is not None and entry[0] <= now < entry[1]
        counted_in = info["rest_tokens"] + (0 if hit else info["prefix_tokens"])

        def reject(kind: str) -> JSONResponse:
            st.stats[f"429_{kind}"] += 1
            return JSONResponse(
                {"error_code": "REQUEST_LIMIT_EXCEEDED",
                 "message": f"REQUEST_LIMIT_EXCEEDED: Exceeded workspace {kind} tokens per minute rate limit for "
                            f"databricks-{short}. Please retry later."},
                status_code=429, headers=hdr)

        if out_b.empty():
            await asyncio.sleep(0.3 / speed)
            return reject("output")
        if in_b.empty():
            await asyncio.sleep(0.3 / speed)
            return reject("input")
        in_b.take(counted_in)

        rng = random.Random(hashlib.sha256((info["user_text"] + info["system_text"][:200]).encode()).digest())
        refusal = "FAKE_REFUSE" in info["system_text"]
        text, think, target = ("", 0, 0) if refusal else make_reply(body, info, rng)
        max_tokens = int(body.get("max_tokens", 1024))
        out_tokens = think + tokens_of(text) if text else think
        stop = "refusal" if refusal else "end_turn"
        if max_tokens <= 0:
            text, out_tokens = "", 0
        elif out_tokens > max_tokens:
            keep = max(0, max_tokens - think)
            text = text[: int(keep * 3.6)]
            out_tokens = max_tokens
            stop = "max_tokens"

        ttft = (args.ttft_s + random.uniform(0, 0.4)) / speed
        gen_s = out_tokens / args.output_tps / speed
        if cacheable and not hit:
            st.cache[key] = (now + ttft, now + ttft + args.cache_ttl_s)
        elif hit:
            st.cache[key] = (entry[0], now + args.cache_ttl_s)
        usage = {"input_tokens": info["rest_tokens"] + (0 if cacheable else info["prefix_tokens"]),
                 "output_tokens": out_tokens,
                 "cache_read_input_tokens": info["prefix_tokens"] if hit else 0,
                 "cache_creation_input_tokens": info["prefix_tokens"] if cacheable and not hit else 0}
        content: list[dict] = []
        if think and ttype == "adaptive" and thinking.get("display") == "summarized":
            content.append({"type": "thinking", "thinking": "Considered the pages and the instructions.", "signature": "fake"})
        if text:
            content.append({"type": "text", "text": text})
        msg = {"id": "msg_" + rid[:20], "type": "message", "role": "assistant", "model": model, "content": content,
               "stop_reason": stop, "stop_sequence": None, "usage": usage}

        def finish() -> None:
            out_b.take(out_tokens)            # charged at completion
            st.stats["ok"] += 1
            st.stats["output_tokens"] += out_tokens
            st.stats["cache_reads"] += 1 if hit else 0
            st.stats["cache_writes"] += 1 if cacheable and not hit else 0
            st.stats["in_flight"] -= 1

        st.stats["in_flight"] += 1
        st.stats["peak_in_flight"] = max(st.stats["peak_in_flight"], st.stats["in_flight"])

        if not body.get("stream"):
            try:
                await asyncio.sleep(ttft + gen_s)
            except asyncio.CancelledError:
                st.stats["in_flight"] -= 1
                raise
            finish()
            return JSONResponse(msg, headers=hdr)

        async def sse():
            def ev(name: str, data: dict) -> bytes:
                return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
            done = False
            try:
                await asyncio.sleep(ttft)
                start = dict(msg, content=[], stop_reason=None, usage=dict(usage, output_tokens=1))
                yield ev("message_start", {"type": "message_start", "message": start})
                for i, block in enumerate(content):
                    if block["type"] == "thinking":
                        yield ev("content_block_start", {"type": "content_block_start", "index": i,
                                                         "content_block": {"type": "thinking", "thinking": "", "signature": ""}})
                        yield ev("content_block_delta", {"type": "content_block_delta", "index": i,
                                                         "delta": {"type": "thinking_delta", "thinking": block["thinking"]}})
                        yield ev("content_block_delta", {"type": "content_block_delta", "index": i,
                                                         "delta": {"type": "signature_delta", "signature": "fake"}})
                    else:
                        yield ev("content_block_start", {"type": "content_block_start", "index": i,
                                                         "content_block": {"type": "text", "text": ""}})
                        t = block["text"]
                        n = max(1, min(60, len(t) // 400 + 1))
                        step = max(1, len(t) // n)
                        for k in range(0, len(t), step):
                            await asyncio.sleep(gen_s / n)
                            yield ev("content_block_delta", {"type": "content_block_delta", "index": i,
                                                             "delta": {"type": "text_delta", "text": t[k:k + step]}})
                    yield ev("content_block_stop", {"type": "content_block_stop", "index": i})
                yield ev("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                                           "usage": {"output_tokens": out_tokens}})
                yield ev("message_stop", {"type": "message_stop"})
                done = True
                finish()
            finally:
                if not done:
                    st.stats["in_flight"] -= 1

        return StreamingResponse(sse(), media_type="text/event-stream", headers=hdr)

    return app


def main() -> None:
    ap = argparse.ArgumentParser(description="Fake gateway for testing the Document Engine. Not the real gateway.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--otpm", type=float, default=100000)
    ap.add_argument("--itpm", type=float, default=1000000)
    ap.add_argument("--bucket", type=float, default=40000, help="output bucket capacity")
    ap.add_argument("--speed", type=float, default=1.0, help="divide every latency by this")
    ap.add_argument("--ttft-s", type=float, default=1.2)
    ap.add_argument("--output-tps", type=float, default=150)
    ap.add_argument("--tokens-per-page", type=int, default=1700)
    ap.add_argument("--cache-min-tokens", type=int, default=1024)
    ap.add_argument("--cache-ttl-s", type=float, default=300)
    ap.add_argument("--max-body-mb", type=float, default=20)
    args = ap.parse_args()
    uvicorn.run(build_app(args), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
