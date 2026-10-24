#!/usr/bin/env python3
"""Run a JSONL file of prompts through the Anthropic Message Batches API (default: Claude Haiku 5.5).

Daniel's default lane for bulk jobs. Batches bill at 50% of the standard rate and usually end
within minutes (the limit is 24 h). Generalised from ASR-Training/scripts/anthropic_batch.py,
which has been in production since 2026-10-21.

Input JSONL, one request per line:
    {"id": "row-1", "user": "...", "system": "... (optional)", "schema": {... JSON Schema, optional}}
With `schema`, the reply is constrained by structured outputs and parsed; without it the text is
returned. Output JSONL, one line per request, keyed by id (batch results are not in input order):
    {"id": "row-1", "result": <parsed JSON or text>}   or   {"id": "row-1", "error": "..."}

Route (picked by the key you hold):
  gateway  --gateway-key NAME, or $LLM_GATEWAY_KEY. Daniel's LiteLLM gateway on residenceserver
           (tailnet only), spend attributed to that consumer's virtual key. Use for projects.
  direct   otherwise: $ANTHROPIC_API_KEY, so run the script under `with-secrets`. Use for one-offs.

Usage:
  with-secrets uv run --with anthropic scripts/anthropic_batch.py in.jsonl out.jsonl
  ... --model claude-sonnet-5-5 --effort medium --max-tokens 4000
  ... --resume msgbatch_...        collect a batch already submitted (the id prints at submit)
  ... --usage-log data/llm-usage.jsonl   append one cost line per batch
"""
import argparse, json, os, socket, subprocess, sys, time, urllib.request
from pathlib import Path

import anthropic

GATEWAY = "http://residencehome.tail9d13b.ts.net:4000/anthropic"
DIRECT = "https://api.anthropic.com"
INFISICAL_PROJECT = "53dc0ba5-4bd1-4b5c-96fc-5e0999aaed78"  # `residence`; envs laptop, desktop
# US$ per million tokens at the standard rate (claude-api skill table, 2026-10-06). Batches bill half.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}
BATCH_DISCOUNT = 0.5


def infisical(name):
    env = "desktop" if "desktop" in socket.gethostname() else "laptop"
    return subprocess.run(["infisical", "secrets", "get", name, "--projectId", INFISICAL_PROJECT,
                           "--env", env, "--plain", "--silent"],
                          check=True, capture_output=True, text=True).stdout.strip()


def resolve(gateway_key_name):
    """(base_url, key, route label). Never prints the key."""
    if gateway_key_name:
        return GATEWAY, os.environ.get(gateway_key_name) or infisical(gateway_key_name), f"gateway:{gateway_key_name}"
    if os.environ.get("LLM_GATEWAY_KEY"):
        return GATEWAY, os.environ["LLM_GATEWAY_KEY"], "gateway:LLM_GATEWAY_KEY"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return DIRECT, os.environ["ANTHROPIC_API_KEY"], "direct"
    sys.exit("no key: run under `with-secrets`, or pass --gateway-key <CONSUMER>_LLM_GATEWAY_KEY")


def params(r, model, max_tokens, effort):
    p = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": r["user"]}]}
    if r.get("system"):
        # cache_control on the system block, not top level: top-level marks the last block (the
        # per-item user message), so every request writes a cache entry and none reads one.
        p["system"] = [{"type": "text", "text": r["system"], "cache_control": {"type": "ephemeral"}}]
    # Haiku 5.5 thinks by default; thinking tokens bill as output. Low effort keeps bulk work cheap.
    cfg = {"effort": effort}
    if r.get("schema"):
        cfg["format"] = {"type": "json_schema", "schema": r["schema"]}
    p["output_config"] = cfg
    return p


def collect(base, key, batch_id, client, poll):
    while (b := client.messages.batches.retrieve(batch_id)).processing_status != "ended":
        c = b.request_counts
        print(f"{batch_id}: {b.processing_status}, {c.processing} processing, {c.succeeded} done", file=sys.stderr)
        time.sleep(poll)
    # Not client.messages.batches.results(): it follows results_url, an absolute api.anthropic.com
    # URL, which bypasses the gateway and 401s for a virtual key. Both routes serve this path.
    req = urllib.request.Request(f"{base}/v1/messages/batches/{batch_id}/results",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    rows, tin, tout = [], 0, 0
    for line in urllib.request.urlopen(req, timeout=300).read().decode().splitlines():
        if not line.strip():
            continue
        res = json.loads(line)
        cid, result = res["custom_id"], res["result"]
        if result["type"] != "succeeded":
            rows.append({"id": cid, "error": result["type"]})
            continue
        msg = result["message"]
        tin += msg["usage"]["input_tokens"] + msg["usage"].get("cache_read_input_tokens", 0) + msg["usage"].get("cache_creation_input_tokens", 0)
        tout += msg["usage"]["output_tokens"]
        if msg["stop_reason"] != "end_turn":
            rows.append({"id": cid, "error": f"stop_reason={msg['stop_reason']}"})
            continue
        text = next(b["text"] for b in msg["content"] if b["type"] == "text")
        rows.append({"id": cid, "result": text, "_parse": True})
    return rows, tin, tout


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("requests")
    ap.add_argument("out")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--effort", default="low", help="low | medium | high")
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--gateway-key", help="Infisical/env name of a gateway virtual key, e.g. ASR_TRAINING_LLM_GATEWAY_KEY")
    ap.add_argument("--resume", help="collect this batch id instead of submitting")
    ap.add_argument("--poll", type=int, default=30)
    ap.add_argument("--usage-log", help="JSONL file to append one cost line to")
    a = ap.parse_args()

    reqs = [json.loads(l) for l in Path(a.requests).read_text().splitlines() if l.strip()]
    schema_ids = {r["id"] for r in reqs if r.get("schema")}
    if len({r["id"] for r in reqs}) != len(reqs):
        sys.exit("ids must be unique")
    base, key, route = resolve(a.gateway_key)
    client = anthropic.Anthropic(base_url=base, api_key=key, max_retries=6)

    if a.resume:
        batch_id = a.resume
    else:
        batch = client.messages.batches.create(requests=[
            {"custom_id": r["id"], "params": params(r, a.model, a.max_tokens, a.effort)} for r in reqs])
        batch_id = batch.id
        print(f"batch {batch_id}: {len(reqs)} requests to {a.model} via {route}", file=sys.stderr)

    rows, tin, tout = collect(base, key, batch_id, client, a.poll)
    for row in rows:
        if row.pop("_parse", False) and row["id"] in schema_ids:
            row["result"] = json.loads(row["result"])
    Path(a.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    pin, pout = PRICES.get(a.model, (None, None))
    cost = None if pin is None else round((tin * pin + tout * pout) / 1e6 * BATCH_DISCOUNT, 6)
    failed = sum("error" in r for r in rows)
    print(f"batch {batch_id}: {len(rows) - failed} ok, {failed} failed, {tin} in / {tout} out tokens, "
          f"~US${cost} (cache reads counted at full input rate, so an upper bound)", file=sys.stderr)
    if a.usage_log:
        Path(a.usage_log).parent.mkdir(parents=True, exist_ok=True)
        with open(a.usage_log, "a") as f:
            f.write(json.dumps({"api": "anthropic-batch", "via": route, "model": a.model, "batch_id": batch_id,
                                "prompt_tokens": tin, "completion_tokens": tout, "cost": cost,
                                "requests": len(rows), "failed": failed,
                                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")


if __name__ == "__main__":
    main()
