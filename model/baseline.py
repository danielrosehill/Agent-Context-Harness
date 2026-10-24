#!/usr/bin/env python3
"""No-GPU baselines, computed once and reused across runs (see docs/eval-plan.md).

    uv run --with scikit-learn --with datasets python baseline.py

- message-only TF-IDF + logistic regression: how far surface wording alone gets. If this is
  high, the dataset has shortcuts and fine-tune numbers overstate real skill.
- message + context TF-IDF: a bag-of-words reference the fine-tune must beat.
"""
import json
from datasets import load_dataset
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from common import REPO, REV, fmt_pair, metrics

import sys
if len(sys.argv) > 1:  # a local data dir, e.g. an unpublished build
    ds = load_dataset("json", data_files={s: f"{sys.argv[1]}/{s}.jsonl" for s in ("train", "validation", "test")}).filter(lambda r: r["agreed"])
else:
    ds = load_dataset(REPO, revision=REV).filter(lambda r: r["agreed"])
y = {s: [int(r["label"] == "new_task") for r in ds[s]] for s in ds}
out = {}
for name, text in [("tfidf_message_only", lambda r: r["message"]),
                   ("tfidf_message_plus_context", lambda r: " || ".join(fmt_pair(r)))]:
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    Xtr = vec.fit_transform([text(r) for r in ds["train"]])
    clf = LogisticRegression(max_iter=2000, C=4).fit(Xtr, y["train"])
    pv = clf.predict_proba(vec.transform([text(r) for r in ds["validation"]]))[:, 1]
    pt = clf.predict_proba(vec.transform([text(r) for r in ds["test"]]))[:, 1]
    out[name] = {"validation": metrics(y["validation"], pv), "test": metrics(y["test"], pt)}
out["always_continue"] = {"test": {"accuracy": 1 - sum(y["test"]) / len(y["test"]), "recall_new_task": 0.0}}
print(json.dumps(out, indent=2))
json.dump(out, open(sys.argv[2] if len(sys.argv) > 2 else "baseline.json", "w"), indent=2)
