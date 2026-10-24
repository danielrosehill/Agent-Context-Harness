#!/usr/bin/env python3
"""Fine-tune a small encoder as a cross-encoder: (message, recent context) -> continue | new_task.

Ladder knobs (custom-model-planning:run-training-job): --train-rows, --eval-rows, --epochs, --lr.
Data: a directory with {train,validation,test}.jsonl in the dataset's row format (uploaded with
the job). Outputs go to $OUT: result.json, the best checkpoint in model/, predictions.

    python train.py --data data --model answerdotai/ModernBERT-base --train-rows 50 --eval-rows 16 --epochs 1
"""
import argparse, collections, json, os, random, time
from pathlib import Path

import numpy as np
import torch
from datasets import Dataset
from transformers import (AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding,
                          Trainer, TrainingArguments)

from common import fmt_pair, metrics

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data")
ap.add_argument("--model", default="answerdotai/ModernBERT-base")
ap.add_argument("--train-rows", type=int, default=0, help="0 = all")
ap.add_argument("--eval-rows", type=int, default=0, help="0 = all; a fixed seeded subset otherwise")
ap.add_argument("--epochs", type=float, default=1)
ap.add_argument("--lr", type=float, default=3e-5)
ap.add_argument("--max-len", type=int, default=512)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--all-rows", action="store_true", help="include generator/verifier disagreements")
a = ap.parse_args()
OUT = Path(os.environ.get("OUT", "out"))
OUT.mkdir(parents=True, exist_ok=True)
t0 = time.time()


def load(split, n):
    rows = [json.loads(l) for l in open(Path(a.data) / f"{split}.jsonl")]
    rows = [r for r in rows if a.all_rows or r.get("agreed", True)]
    if n:
        rows = random.Random(0).sample(rows, min(n, len(rows)))  # fixed subset across runs
    return rows


splits = {"train": load("train", a.train_rows), "validation": load("validation", a.eval_rows),
          "test": load("test", a.eval_rows)}
tok = AutoTokenizer.from_pretrained(a.model)


def encode(rows):
    m, c = zip(*(fmt_pair(r) for r in rows))
    enc = tok(list(m), list(c), truncation="only_second", max_length=a.max_len)
    enc["labels"] = [int(r["label"] == "new_task") for r in rows]
    return Dataset.from_dict(dict(enc))


ds = {s: encode(r) for s, r in splits.items()}
model = AutoModelForSequenceClassification.from_pretrained(
    a.model, num_labels=2, id2label={0: "continue", 1: "new_task"}, label2id={"continue": 0, "new_task": 1})


def probs(dset):
    logits = trainer.predict(dset).predictions
    logits = logits[0] if isinstance(logits, tuple) else logits
    return torch.softmax(torch.tensor(logits, dtype=torch.float32), -1)[:, 1].numpy()


def compute(ev):
    logits = ev.predictions[0] if isinstance(ev.predictions, tuple) else ev.predictions
    p = torch.softmax(torch.tensor(logits, dtype=torch.float32), -1)[:, 1].numpy()
    return metrics(list(ev.label_ids), list(p))


args = TrainingArguments(
    output_dir=str(OUT / "ckpt"), num_train_epochs=a.epochs, learning_rate=a.lr,
    per_device_train_batch_size=a.batch, per_device_eval_batch_size=64,
    warmup_steps=max(1, int(0.1 * a.epochs * -(-len(splits['train']) // a.batch))),  # v5 dropped warmup_ratio
    weight_decay=0.01, lr_scheduler_type="linear", bf16=torch.cuda.is_available(),
    eval_strategy="epoch", save_strategy="epoch", save_total_limit=1, load_best_model_at_end=True,
    metric_for_best_model="auc_pr", logging_steps=20, report_to=[], seed=0)
trainer = Trainer(model=model, args=args, train_dataset=ds["train"], eval_dataset=ds["validation"],
                  data_collator=DataCollatorWithPadding(tok), compute_metrics=compute)
trainer.train()

result = {"args": vars(a), "rows": {s: len(r) for s, r in splits.items()}}
for s in ("validation", "test"):
    p = probs(ds[s])
    y = [int(r["label"] == "new_task") for r in splits[s]]
    result[s] = metrics(y, list(p))
    by_kind = collections.defaultdict(list)
    for r, pi in zip(splits[s], p):
        by_kind[r["kind"]].append((pi >= 0.5) == (r["label"] == "new_task"))
    result[s]["accuracy_by_kind"] = {k: round(sum(v) / len(v), 3) for k, v in sorted(by_kind.items())}
    # Matched pairs (v0.2): the same message under both labels; both must be right.
    pairs = collections.defaultdict(list)
    for r, pi in zip(splits[s], p):
        if r.get("pair_id"):
            pairs[r["pair_id"]].append((pi >= 0.5) == (r["label"] == "new_task"))
    full = [all(v) for v in pairs.values() if len(v) == 2]
    if full:
        result[s]["pair_accuracy"] = round(sum(full) / len(full), 4)
        result[s]["pairs"] = len(full)
    with open(OUT / f"pred-{s}.jsonl", "w") as f:
        for r, pi in zip(splits[s], p):
            f.write(json.dumps({"id": r["id"], "kind": r["kind"], "label": r["label"], "p_new_task": round(float(pi), 4)}) + "\n")
result["minutes"] = round((time.time() - t0) / 60, 2)
result["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
trainer.save_model(str(OUT / "model"))
tok.save_pretrained(str(OUT / "model"))
json.dump(result, open(OUT / "result.json", "w"), indent=2)
print(json.dumps(result, indent=2))
