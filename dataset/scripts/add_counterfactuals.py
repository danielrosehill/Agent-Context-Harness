#!/usr/bin/env python3
"""v0.2: merge matched-pair rows into the built splits, in place.

    python3 build_dataset.py ../raw/requests-gen.jsonl ../raw/out-gen.jsonl ../raw/out-verify.jsonl ../hf
    python3 add_counterfactuals.py ../hf/data ../raw/out-cf-shaped.jsonl ../raw/out-verify-cf.jsonl

Each agreed new_task row gets a `pair_id`. Its partner is a new row with the identical message, a
generated context in which that message continues the work, label `continue`, kind
`counterfactual_continue`, and the same split as the source, so a message never crosses splits.
"""
import collections, json, sys
from pathlib import Path

data, shaped_path, ver_path = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
shaped = {r["id"]: r["result"] for r in map(json.loads, open(shaped_path))}
vers = {r["id"]: r.get("result") for r in map(json.loads, open(ver_path))}
stats = collections.Counter()
for split in ("train", "validation", "test"):
    rows = [json.loads(l) for l in open(data / f"{split}.jsonl")]
    rows = [r for r in rows if r["kind"] != "counterfactual_continue"]  # idempotent re-runs
    extra = []
    for r in rows:
        r["pair_id"] = None
        cid = f"cf-{r['id']}"
        if cid not in shaped:
            continue
        v = vers.get(cid)
        if not isinstance(v, dict) or not v.get("labels"):
            stats["cf_dropped_no_verifier"] += 1
            continue
        vl = v["labels"][0]
        res = shaped[cid]
        r["pair_id"] = r["id"]
        extra.append({**r, "id": cid, "workspace": res["workspace"], "context": res["turns"],
                      "label": "continue", "kind": "counterfactual_continue",
                      "rationale": res["candidates"][0]["rationale"], "verifier_label": vl["label"],
                      "verifier_confidence": vl["confidence"], "agreed": vl["label"] == "continue",
                      "pair_id": r["id"]})
        stats[f"cf_{split}"] += 1
        stats["cf_agreed" if vl["label"] == "continue" else f"cf_verifier_{vl['label']}"] += 1
    with open(data / f"{split}.jsonl", "w") as f:
        for r in rows + extra:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats[f"rows_{split}"] = len(rows) + len(extra)
print(json.dumps(dict(sorted(stats.items())), indent=2))
