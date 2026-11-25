"""Preflight and the bucket probe: the two commands that talk to the gateway outside a job.

preflight      cheap. Checks the config, the database, and for every model: that it answers, which
               "thinking off" form it accepts, and that adaptive thinking is accepted.
probe bucket   saturates one model on purpose to find where rejection begins. Needs --confirm-saturation.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, Section, placeholders
from .db import Db, missing_tables
from .gateway import execute_call, make_client

PROBE_PROMPT = ("Write a numbered list of 150 short, plain facts about office buildings, one per line. "
                "Do not add an introduction or a closing remark.")


async def cmd_preflight(cfg: Section) -> int:
    ok = True
    print("== config ==")
    ph = placeholders(cfg)
    print(f"  file: {cfg['_path']}")
    if ph:
        print("  FILL-IN values remain: " + ", ".join(ph))
        ok = False
    else:
        print("  no FILL-IN values remain")

    print("== database ==")
    db = Db(cfg)
    try:
        row = await db.fetchone("SELECT version() AS v, clock_timestamp() AS now")
        print(f"  connected: {row['v'].split(',')[0]}")
        t0 = time.monotonic()
        for _ in range(20):
            await db.fetchone("SELECT 1 AS x")
        print(f"  round trip: {(time.monotonic() - t0) / 20 * 1000:.1f} ms average over 20 queries")
        miss = await missing_tables(db)
        print("  tables: all present" if not miss else f"  tables missing ({', '.join(miss)}). Run `python -m doc_engine db init`.")
        ok = ok and not miss
        try:
            conn = await db.connect()
            await conn.execute("LISTEN de_wake")
            await conn.close()
            print("  LISTEN/NOTIFY: available")
        except Exception as e:
            print(f"  LISTEN/NOTIFY: not available ({str(e).strip()}). The engine falls back to timed checks. "
                  f"(A note, not counted as a problem.)")
    except Exception as e:
        print(f"  FAILED: {e}")
        ok = False
    finally:
        await db.close()

    print("== gateway ==")
    if "gateway.base_url" in ph:
        print("  skipped: gateway.base_url is not set")
        print("\npreflight found problems (see above)")
        return 1
    client = make_client(cfg)
    forms = {"disabled": {"thinking": {"type": "disabled"}},
             "between_tools": {"thinking": {"type": "between_tools"}},
             "effort_low": {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}}
    try:
        for key, m in cfg.models.items():
            print(f"  {key} ({m.gateway_name})")
            base = {"model": m.gateway_name, "max_tokens": 64,
                    "messages": [{"role": "user", "content": "Reply with the single word: ready"}]}
            want = m.get("thinking_off", "disabled")
            works: str | None = want         # the "thinking off" form this model accepts, used for the image check
            res = await execute_call(client, cfg, {**base, **forms[want]})
            if res.outcome == "ok":
                print(f"    thinking off as '{want}': OK  ({res.input_tokens} in, {res.output_tokens} out, "
                      f"{res.duration_s:.1f}s, reply {res.text.strip()[:30]!r})")
            else:
                ok = False
                works = None
                print(f"    thinking off as '{want}': {res.outcome} HTTP {res.http_status}: {_msg(res)}")
                for alt, extra in forms.items():
                    if alt == want:
                        continue
                    r2 = await execute_call(client, cfg, {**base, **extra})
                    print(f"      trying '{alt}': {r2.outcome}" + ("" if r2.outcome == "ok" else f" ({_msg(r2)[:120]})"))
                    if r2.outcome == "ok":
                        print(f"      -> set models.{key}.thinking_off: {alt}")
                        works = alt
                        break
            r3 = await execute_call(client, cfg, {**base, "max_tokens": 600,
                                                  "thinking": {"type": "adaptive", "display": "summarized"},
                                                  "output_config": {"effort": "low"}})
            print(f"    adaptive thinking, low effort: {r3.outcome}" + ("" if r3.outcome == "ok" else f" HTTP {r3.http_status}: {_msg(r3)[:160]}"))
            ok = ok and r3.outcome == "ok"
            if works is None:
                print("    image input: not checked, because no \"thinking off\" form was accepted. Fix that first.")
                continue
            r4 = await execute_call(client, cfg, {**base, **forms[works], "messages": [{"role": "user", "content": [
                _test_image(), {"type": "text", "text": "Reply with the number shown in the image and nothing else."}]}]})
            if r4.outcome == "ok":
                seen = "read correctly" if "742" in r4.text else f"reply {r4.text.strip()[:30]!r}, expected 742"
                print(f"    image input: OK  ({seen}, {r4.input_tokens} in)")
            else:
                print(f"    image input: {r4.outcome} HTTP {r4.http_status}: {_msg(r4)[:160]}")
                if str(cfg.worker.get("send_images_as", "image")).lower() == "pdf":
                    print("      (not a problem: worker.send_images_as is pdf, so images are sent inside a PDF)")
                else:
                    ok = False
                    print("      -> image files cannot be sent as images to this model. Set worker.send_images_as: pdf")
    finally:
        await client.close()
    print("\npreflight " + ("passed" if ok else "found problems (see above)"))
    return 0 if ok else 1


def _test_image() -> dict:
    """A small PNG showing the number 742, as an image content block."""
    import base64
    import io

    from PIL import Image, ImageDraw

    from .samples import _font
    img = Image.new("RGB", (320, 140), (255, 255, 255))
    ImageDraw.Draw(img).text((90, 30), "742", fill=(0, 0, 0), font=_font(64))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode("ascii")}}


def _msg(res) -> str:
    e = res.error or {}
    b = e.get("body")
    if isinstance(b, dict):
        return str(b.get("message") or b)
    return str(e.get("message") or b or "")


PROBE_MAX_TOKENS = 1500


def probe_spacing(otpm: float) -> float:
    """Seconds between calls so that replies charge about twice what the bucket regains. Slow enough to see
    where the bucket overflows, fast enough that it does."""
    refill = max(1.0, float(otpm) / 60.0)
    return round(min(5.0, max(0.05, PROBE_MAX_TOKENS / (2.0 * refill))), 2)


def bucket_bounds(records: list[dict], rate: float) -> dict | None:
    """The gateway's output bucket, from the calls of one probe run.

    The gateway charges a call's output when the call completes, regains `rate` tokens a second, and cannot
    regain more than a full bucket: before the first reply completes, nothing is regained at all. So the amount
    in use is followed call by call, never below zero. The bucket is at least the most that was in use when an
    accepted call was sent, and less than what was in use when the first rejected call was sent."""
    rej = sorted((r for r in records if r["outcome"] == "429"), key=lambda r: r["sent_s"])
    ok = [r for r in records if r["outcome"] == "ok"]
    if not rej or not ok:
        return None
    t_rej = rej[0]["sent_s"]
    done = sorted((r for r in ok if r["done_s"] <= t_rej), key=lambda r: r["done_s"])

    def in_use(t: float) -> float:
        level, at = 0.0, 0.0
        for r in done:
            if r["done_s"] > t:
                break
            level = max(0.0, level - rate * (r["done_s"] - at)) + r["output_tokens"]
            at = r["done_s"]
        return max(0.0, level - rate * (t - at))

    sends = [r["sent_s"] for r in ok if r["sent_s"] < t_rej]
    # Replies arrive in bursts, so the amount in use can have been a little higher at an accepted call than it
    # was at the first rejected one. The two figures are reported in order either way.
    low, high = sorted((max((in_use(t) for t in sends), default=0.0), in_use(t_rej)))
    first_done = done[0]["done_s"] if done else t_rej
    recent = [r for r in done if r["done_s"] > t_rej - 2.0]
    window = min(2.0, max(0.1, t_rej - first_done))
    return {"first_rejected_sent_s": t_rej, "first_completion_s": first_done, "completed_before": len(done),
            "output_before": sum(r["output_tokens"] for r in done),
            "regained": sum(r["output_tokens"] for r in done) - high,
            "bucket_low": low, "bucket_high": high,
            "charge_per_s": sum(r["output_tokens"] for r in recent) / window,
            "accepted_after": len([r for r in ok if r["sent_s"] > t_rej])}


async def cmd_probe_bucket(cfg: Section, args: argparse.Namespace) -> int:
    if args.model not in cfg.models:
        print(f"model {args.model!r} is not configured (configured: {', '.join(cfg.models)})")
        return 1
    m = cfg.models[args.model]
    per_call = PROBE_MAX_TOKENS
    if args.spacing is None:
        args.spacing = probe_spacing(m.otpm)
    est_out = args.calls * per_call
    cost = est_out * m.pricing.output / 1e6 + args.calls * 60 * m.pricing.input / 1e6
    print(f"bucket probe on {args.model} ({m.gateway_name})")
    print(f"  up to {args.calls} calls, one every {args.spacing}s, up to {per_call} output tokens each")
    print(f"  at most about {est_out:,} output tokens, about ${cost:.2f}; stops 20 s after the first rejection")
    print(f"  configured OTPM {m.otpm:,.0f}")
    if args.dry_run:
        return 0
    if not args.confirm_saturation:
        print("\nThis saturates the model on purpose and throttles every application using it.\n"
              "Re-run with --confirm-saturation when you are ready.")
        return 2

    client = make_client(cfg)
    off = {"disabled": {"thinking": {"type": "disabled"}}, "between_tools": {"thinking": {"type": "between_tools"}},
           "effort_low": {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}}[m.get("thinking_off", "disabled")]
    params = {"model": m.gateway_name, "max_tokens": PROBE_MAX_TOKENS, "messages": [{"role": "user", "content": PROBE_PROMPT}], **off}
    t0 = time.monotonic()
    records: list[dict] = []
    first_429: list[float] = []

    async def one(i: int) -> None:
        sent = time.monotonic() - t0
        res = await execute_call(client, cfg, params)
        done = time.monotonic() - t0
        if res.outcome == "429" and not first_429:
            first_429.append(done)
        records.append({"i": i, "sent_s": round(sent, 3), "done_s": round(done, 3), "outcome": res.outcome,
                        "http_status": res.http_status, "output_tokens": res.output_tokens,
                        "limit_type": res.limit_type, "error": res.error})

    tasks = []
    try:
        for i in range(args.calls):
            if first_429 and time.monotonic() - t0 > first_429[0] + 20:
                break
            tasks.append(asyncio.create_task(one(i)))
            await asyncio.sleep(args.spacing)
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        for t in tasks:
            t.cancel()
        print("stopped")
    finally:
        await client.close()

    records.sort(key=lambda r: r["i"])
    ok = [r for r in records if r["outcome"] == "ok"]
    rej = [r for r in records if r["outcome"] == "429"]
    rate = float(m.otpm) / 60.0
    print(f"\n  sent {len(records)}, accepted {len(ok)}, rejected {len(rej)}")
    result: dict = {"model": args.model, "gateway_name": m.gateway_name, "otpm": m.otpm, "spacing_s": args.spacing,
                    "sent": len(records), "accepted": len(ok), "rejected": len(rej)}
    b = bucket_bounds(records, rate)
    if b:
        t1 = b["first_rejected_sent_s"]
        in_flight = len([r for r in ok if r["sent_s"] <= t1 < r["done_s"]])
        dur = sum(r["done_s"] - r["sent_s"] for r in ok) / max(1, len(ok))
        after = [r for r in ok if r["sent_s"] > t1]
        span = max((r["done_s"] for r in records), default=t1) - t1
        low, high = b["bucket_low"], b["bucket_high"]
        coarse = b["charge_per_s"] > max(1.0, high) / 5.0       # one second of replies moves the answer by a fifth
        result.update({"first_429_s": t1, "first_completion_s": b["first_completion_s"],
                       "completed_before": b["completed_before"], "output_before": b["output_before"],
                       "regained_before": b["regained"], "in_flight_at_first_429": in_flight, "mean_call_s": dur,
                       "bucket_low": low, "bucket_high": high, "bucket_estimate": low,
                       "charge_per_s_at_first_429": b["charge_per_s"], "accepted_after_first_429": b["accepted_after"],
                       "coarse": coarse,
                       "limit_types": sorted({r["limit_type"] for r in rej if r["limit_type"]}),
                       "sample_429": rej[0]["error"],
                       "accepted_output_per_min_after": (sum(r["output_tokens"] for r in after) / span * 60) if span > 5 else None})
        print(f"  first rejection at t+{t1:.1f}s; {b['completed_before']} calls had completed with "
              f"{b['output_before']:,} output tokens; {in_flight} in flight")
        print(f"  first reply completed at t+{b['first_completion_s']:.1f}s; regained since then at the configured OTPM: "
              f"{b['regained']:,.0f}")
        print(f"  => the bucket holds between {low:,.0f} and {high:,.0f} output tokens")
        print(f"  replies were being charged at about {b['charge_per_s']:,.0f} tokens a second when the rejection came; "
              f"{b['accepted_after']} call(s) were still accepted after it")
        print(f"  mean call duration {dur:.1f}s; rejection names: {', '.join(result['limit_types']) or 'unknown'}")
        if result["accepted_output_per_min_after"]:
            print(f"  after the first rejection the gateway accepted about {result['accepted_output_per_min_after']:,.0f} output tokens per minute")
        if coarse:
            print(f"\n  This run is too coarse to rely on: one second of replies is {b['charge_per_s']:,.0f} tokens, a large\n"
                  f"  part of the result. Wait until the model has been idle for a while, then run again with a larger\n"
                  f"  --spacing (leave --spacing out to let the probe choose: {probe_spacing(m.otpm)}s for this model).")
        else:
            print(f"\n  To use this: set models.{args.model}.bucket_measured to about {low:,.0f}. Keep bucket_capacity_output\n"
                  f"  until the result has been reviewed. The bucket must have been full at the start: run this only\n"
                  f"  after the model has been idle for a while.")
    elif not ok:
        errs = [r for r in records if r.get("error")]
        first = errs[0] if errs else {}
        print(f"  no call succeeded, so nothing was measured. First failure: {first.get('outcome', 'unknown')}"
              f"{' (HTTP ' + str(first['http_status']) + ')' if first.get('http_status') else ''}: "
              f"{str(first.get('error') or 'no detail')[:400]}")
        print("  Check gateway.base_url, the token and the model's gateway_name, then run preflight.")
        result["error"] = "no call succeeded"
    else:
        total = sum(r["output_tokens"] for r in ok)
        print(f"  no rejection: {total:,} output tokens accepted in {max(r['done_s'] for r in ok):.0f}s. "
              f"Increase --calls or lower --spacing.")
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    f = out_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}_probe_bucket_{args.model}.json"
    f.write_text(json.dumps({"result": result, "calls": records}, indent=1, default=str))
    print(f"  raw data: {f}")
    return 0 if ok else 1
