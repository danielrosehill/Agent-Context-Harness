#!/usr/bin/env python3
"""Export a trained checkpoint to ONNX, quantise it to int8, check agreement and time it on CPU.

    python export_onnx.py MODEL_DIR OUT_DIR [--data data] [--n 300]

Writes OUT_DIR/model.onnx (fp32), OUT_DIR/model.int8.onnx (dynamic int8, onnxruntime) and the
tokenizer files, and prints JSON: test metrics for torch / fp32 / int8 on the first --n test rows,
and latency (p50/p95 ms, one input at a time, as the hook runs) at 128 tokens, at 512 tokens,
and on real test rows.
"""
import argparse, json, shutil, statistics, sys, time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import AutoModelForSequenceClassification, AutoTokenizer

sys.path.insert(0, str(Path(__file__).parent))
from common import fmt_pair, metrics  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--data", default="data")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(a.model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(a.model_dir, attn_implementation="eager").eval()
    ex = tok("hello", "world", return_tensors="pt")
    fp32, int8 = out / "model.onnx", out / "model.int8.onnx"
    torch.onnx.export(
        model, (ex["input_ids"], ex["attention_mask"]), str(fp32),
        input_names=["input_ids", "attention_mask"], output_names=["logits"],
        dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}, "logits": {0: "b"}},
        opset_version=17, dynamo=False,
    )
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    tok.save_pretrained(out)
    shutil.copy(Path(a.model_dir) / "config.json", out / "config.json")

    rows = [json.loads(l) for l in open(Path(a.data) / "test.jsonl")]
    rows = [r for r in rows if r["agreed"]][: a.n]
    y = [int(r["label"] == "new_task") for r in rows]
    enc = [tok(*fmt_pair(r), truncation="only_second", max_length=a.max_len, return_tensors="np") for r in rows]

    so = ort.SessionOptions()
    so.intra_op_num_threads = a.threads
    sess = {k: ort.InferenceSession(str(p), so, providers=["CPUExecutionProvider"]) for k, p in (("fp32", fp32), ("int8", int8))}

    def p_new(logits):
        z = np.exp(logits - logits.max(-1, keepdims=True))
        return float((z / z.sum(-1, keepdims=True))[0, 1])

    probs = {"torch": [], "fp32": [], "int8": []}
    with torch.no_grad():
        for e in enc:
            probs["torch"].append(p_new(model(input_ids=torch.tensor(e["input_ids"]),
                                              attention_mask=torch.tensor(e["attention_mask"])).logits.numpy()))
    for k, s in sess.items():
        for e in enc:
            probs[k].append(p_new(s.run(None, {"input_ids": e["input_ids"], "attention_mask": e["attention_mask"]})[0]))

    def bench(s, feeds, reps):
        for f in feeds[:3]:
            s.run(None, f)
        ts = []
        for i in range(reps):
            f = feeds[i % len(feeds)]
            t = time.perf_counter()
            s.run(None, f)
            ts.append((time.perf_counter() - t) * 1000)
        ts.sort()
        return {"p50_ms": round(statistics.median(ts), 1), "p95_ms": round(ts[int(0.95 * len(ts)) - 1], 1)}

    def fixed(n):
        return [{"input_ids": np.full((1, n), tok.pad_token_id + 1, dtype=np.int64), "attention_mask": np.ones((1, n), dtype=np.int64)}]

    real = [{"input_ids": e["input_ids"], "attention_mask": e["attention_mask"]} for e in enc]
    lens = sorted(e["input_ids"].shape[1] for e in enc)
    res = {
        "n": len(rows), "threads": a.threads,
        "real_tokens": {"p50": lens[len(lens) // 2], "p95": lens[int(0.95 * len(lens)) - 1], "max": lens[-1]},
        "size_mb": {k: round(p.stat().st_size / 1e6, 1) for k, p in (("fp32", fp32), ("int8", int8))},
        "metrics": {k: metrics(y, v) for k, v in probs.items()},
        "max_abs_diff_vs_torch": {k: round(max(abs(a_ - b) for a_, b in zip(probs[k], probs["torch"])), 4) for k in ("fp32", "int8")},
        "latency": {k: {"tok128": bench(s, fixed(128), 50), "tok512": bench(s, fixed(512), 30), "real": bench(s, real, 100)}
                    for k, s in sess.items()},
    }
    print(json.dumps(res, indent=2))
    (out / "export.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
