#!/usr/bin/env python3
"""Reshape counterfactual generator output into verify_requests.py's input (one candidate each).

    python3 cf_to_verify.py ../raw/requests-cf.jsonl ../raw/out-cf.jsonl ../hf/data > ../raw/out-cf-shaped.jsonl
"""
import json, sys
from pathlib import Path

reqs = {r["id"]: r for r in map(json.loads, open(sys.argv[1]))}
msgs = {r["id"]: r["message"] for f in Path(sys.argv[3]).glob("*.jsonl") for r in map(json.loads, open(f))}
for g in map(json.loads, open(sys.argv[2])):
    res = g.get("result")
    if not isinstance(res, dict):
        continue
    res["candidates"] = [{"message": msgs[reqs[g["id"]]["source"]], "label": "continue",
                          "kind": "counterfactual_continue", "rationale": res.pop("why", "")}]
    print(json.dumps({"id": g["id"], "result": res}))
