#!/usr/bin/env python3
"""Join generator and verifier batch outputs into flat rows, split by scenario.

    python3 build_dataset.py ../raw/requests-gen.jsonl ../raw/out-gen.jsonl ../raw/out-verify.jsonl ../hf

Writes <out>/data/{train,validation,test}.jsonl and prints a summary as JSON. All six candidates of
a scenario share its context, so splits are made per scenario (hash of scenario_id: 80/10/10),
never per row, or the test set would leak contexts seen in training.
"""
import collections, hashlib, json, sys
from pathlib import Path

GENERATOR, VERIFIER = "claude-haiku-5-5", "claude-sonnet-5-5"


def load(path):
    return {r["id"]: r for r in map(json.loads, open(path))}


def split_of(scenario_id):
    b = int(hashlib.sha256(scenario_id.encode()).hexdigest(), 16) % 10
    return "test" if b == 0 else "validation" if b == 1 else "train"


def main(req_path, gen_path, ver_path, out_dir):
    reqs, gens, vers = load(req_path), load(gen_path), load(ver_path)
    out = Path(out_dir) / "data"
    out.mkdir(parents=True, exist_ok=True)
    files = {s: open(out / f"{s}.jsonl", "w") for s in ("train", "validation", "test")}
    stats = collections.Counter()
    for sid, g in sorted(gens.items()):
        r = g.get("result")
        v = (vers.get(sid) or {}).get("result")
        if not isinstance(r, dict) or not isinstance(v, dict) or len(r.get("candidates", [])) != 6:
            stats["scenarios_dropped"] += 1
            continue
        seed = reqs[sid]["seed"]
        vlabels = {x["index"]: x for x in v["labels"]}
        split = split_of(sid)
        stats["scenarios"] += 1
        for i, c in enumerate(r["candidates"]):
            vl = vlabels.get(i)
            if vl is None:
                stats["rows_dropped_no_verifier"] += 1
                continue
            row = {
                "id": f"{sid}-{i}",
                "scenario_id": sid,
                "agent_kind": seed["agent"],
                "domain": seed["domain"],
                "task": seed.get("task"),
                "user_style": seed["style"],
                "workspace": r["workspace"],
                "context": r["turns"],
                "message": c["message"],
                "label": c["label"],
                "kind": c["kind"],
                "rationale": c["rationale"],
                "verifier_label": vl["label"],
                "verifier_confidence": vl["confidence"],
                "agreed": vl["label"] == c["label"],
                "generator_model": GENERATOR,
                "verifier_model": VERIFIER,
            }
            files[split].write(json.dumps(row, ensure_ascii=False) + "\n")
            stats[f"rows_{split}"] += 1
            stats[f"label_{c['label']}"] += 1
            stats["rows_agreed" if row["agreed"] else "rows_disagreed"] += 1
    for f in files.values():
        f.close()
    print(json.dumps(dict(sorted(stats.items())), indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:5])
