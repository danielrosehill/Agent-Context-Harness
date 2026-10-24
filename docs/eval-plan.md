# Eval plan: local task-break classifier

Written 2026-10-24, before the first probe. It covers the classifier in
[`local-classifier-plan.md`](local-classifier-plan.md) and is trained by [`../model/`](../model/).

## Task

Input: (new user message, recent context: up to 4 exchanges, newest first). Output: `p(new_task)`.
The hook splits only above a threshold, so the operating point is **high precision on
`new_task`**.

## Pass bar

| Metric | Bar | On |
|---|---|---|
| `new_task` recall at precision ≥ 0.95 | ≥ 0.50 | v0.2 test split (synthetic), and later the gold set |
| Pair accuracy (both members of a matched pair right) | ≥ 0.80, and well above the message-only baseline | v0.2 test split |
| Latency, int8 ONNX, laptop CPU | p95 < 200 ms | 512-token inputs |
| Undo rate in live use | < 1 in 10 splits | L5 |

The synthetic test split is a development signal only. The release number is the **gold set**
(L2: Daniel's own sessions, hand-labelled, never trained on), which doesn't exist yet.

## Baselines (computed once, `model/baseline.py` → `model/baseline.json`)

v0.1 (2026-10-24, agreed rows, test n=493):

| Baseline | Accuracy | AUC-PR | Recall @ P95 |
|---|---|---|---|
| Always `continue` | 0.566 | — | 0 |
| TF-IDF, **message only** | 0.968 | 0.997 | 0.981 |
| TF-IDF, message + context | 0.852 | 0.899 | 0.430 |

**v0.1 can be solved from the message alone.** Continue messages refer back ("same", "it",
"that", "too": 88% contain one) and new-task messages are self-contained requests. A model
trained on it would learn to detect pronouns, which fails on real sessions: "backfill the
currency column" continues a session that has been migrating payments. Hence v0.2's matched
pairs. Every agreed `new_task` message also appears, unchanged, with a generated context in
which it continues the work. The message-only baseline has to drop towards chance on those pairs
before fine-tune numbers mean anything.

v0.2 (2026-10-24, agreed rows incl. 1,284 counterfactual pairs; validation n=697 / 144 pairs,
test n=608):

| Baseline | Split | Accuracy | AUC-PR | Recall @ P95 |
|---|---|---|---|---|
| Always `continue` | test | 0.648 | — | 0 |
| TF-IDF, message only | test | 0.793 | 0.758 | 0.037 |
| TF-IDF, message + context | test | 0.760 | 0.781 | 0.140 |

The pairs did their job: message-only recall at P95 fell from 0.981 to 0.037.

## Runs

All on Modal (personal workspace, app `ai-training`, volume `ai-training:/data/runs/<run>`),
`model/train.py`, v0.2 data uploaded from `model/data/`, batch 16, max_len 512, L4 GPU.
Metrics are on validation unless marked; pair accuracy = both members of a pair right.

| Run | Rung | Model | Data / epochs / lr | Min | Acc | AUC-PR | R@P95 | Pair acc | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| `atbd-r1-*` | probe | ModernBERT-base, Ettin-150M | 1k rows / 1 / 5e-5 | ~1 | — | — | — | 0.0 / 0.007 | no-go: both collapsed to `continue` (loss 0.74→0.65), undertrained |
| `atbd-r2-modernbert-full1ep` | probe | `answerdotai/ModernBERT-base` | all agreed / 1 / 5e-5 | 2.4 | 0.966 | 0.992 | 0.958 | 0.868 | **go** |
| `atbd-r2-ettin150-full1ep` | probe | `jhu-clsp/ettin-encoder-150m` | all agreed / 1 / 5e-5 | 2.4 | 0.769 | 0.803 | 0.025 | 0.257 | no-go at these settings |
| `atbd-r3-modernbert-full3ep` | full | `answerdotai/ModernBERT-base` | all agreed / 3 / 5e-5 | 6.9 | 0.960 | 0.991 | 0.925 | 0.840 | borderline: no better than r2 on validation |

r2 ModernBERT accuracy by kind (validation): counterfactual_continue 0.917, far 0.99, follow_up
0.981, hard_negative 1.0, implicit_reference 1.0, same_workspace 0.934, subtle_pivot 0.93. The
weakest slots are the ones that need the context, as expected.

Test split (n=608, 115 pairs), looked at once per run:

| Run | Acc | AUC-PR | R@P95 | Pair acc |
|---|---|---|---|---|
| r2 (1 epoch) | 0.942 | 0.980 | 0.883 | 0.774 |
| r3 (3 epochs) | 0.951 | 0.986 | 0.902 | 0.791 |

Recall clears its bar easily. **Pair accuracy on test sits just under 0.80** (one pair short at
n=115, so within noise), against 0 for the message-only baseline. The weak kinds are
`counterfactual_continue` (0.896) and `same_workspace` (0.867): the cases where the message alone
looks self-contained and only the context decides. More epochs did not fix it. The next lever is
the data (more pairs, and pairs for `same_workspace`), not training length. The real verdict
still waits on the L2 gold set.
