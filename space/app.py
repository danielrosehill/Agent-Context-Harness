"""Explainer and demo Space for danielrosehill/Agent-Task-Break-Detector-ModernBERT.

Runs the int8 ONNX export on CPU with the same input format as model/common.py:fmt_pair
(last 4 exchanges, newest first, "AGENT: ...\nUSER: ...", truncation="only_second", max 512).
"""

import json
from pathlib import Path

import gradio as gr
import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

REPO = "danielrosehill/Agent-Task-Break-Detector-ModernBERT"
cfg = json.load(open(hf_hub_download(REPO, "new_task_split.json")))
THRESHOLD = cfg["threshold"]
MAX_LEN = cfg["max_len"]
MAX_TURNS = cfg["max_turns"]

tok = Tokenizer.from_file(hf_hub_download(REPO, cfg["tokenizer"]))
tok.enable_truncation(MAX_LEN, strategy="only_second")
sess = ort.InferenceSession(hf_hub_download(REPO, cfg["onnx"]), providers=["CPUExecutionProvider"])

EXAMPLES = json.load(open(Path(__file__).parent / "examples.json"))


def parse_context(text):
    """Lines starting USER: / AGENT:, oldest first. Continuation lines join the previous turn."""
    turns, cur, role = [], {}, None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        up = s.upper()
        if up.startswith("USER:"):
            if cur.get("user") is not None:
                turns.append(cur)
                cur = {}
            role, cur["user"] = "user", s[5:].strip()
        elif up.startswith("AGENT:"):
            role, cur["agent"] = "agent", s[6:].strip()
        elif role:
            cur[role] += " " + s
    if cur:
        turns.append(cur)
    return [{"user": t.get("user", ""), "agent": t.get("agent", "")} for t in turns]


def format_context(turns):
    return "\n".join(f"USER: {t['user']}\nAGENT: {t['agent']}" for t in turns)


def model_input(turns):
    recent = turns[-MAX_TURNS:][::-1]
    return "\n".join(f"AGENT: {t['agent']}\nUSER: {t['user']}" for t in recent)


def classify(message, context_text):
    if not message.strip():
        return {}, "Type a new user message first."
    turns = parse_context(context_text)
    enc = tok.encode(message.strip(), model_input(turns)) if turns else tok.encode(message.strip())
    ids = np.array([enc.ids], dtype=np.int64)
    mask = np.array([enc.attention_mask], dtype=np.int64)
    logits = sess.run(None, {"input_ids": ids, "attention_mask": mask})[0][0]
    p = np.exp(logits - logits.max())
    p = p / p.sum()
    p_new = float(p[1])
    if p_new >= THRESHOLD:
        verdict = f"### New task → start a fresh session\n`p(new_task)` = **{p_new:.3f}**, at or above the threshold of {THRESHOLD}."
    else:
        verdict = f"### Continue → keep the current session\n`p(new_task)` = **{p_new:.3f}**, below the threshold of {THRESHOLD}."
    verdict += f"\n\nThe model read {min(len(turns), MAX_TURNS)} of {len(turns)} exchanges and {len(enc.ids)} tokens."
    return {"new_task": p_new, "continue": 1 - p_new}, verdict


def example_rows():
    rows = []
    for e in EXAMPLES:
        rows.append([e["message"], format_context(e["context"])])
    return rows


INTRO = f"""
# Agent Task Break Detector

You are deep in a session with a coding agent, and you type something unrelated: a different bug, an idea, an errand.
The agent now carries all the earlier history into a task that doesn't need it. That costs tokens, and stale context
makes its answers worse. The tidy fix is a fresh session (`/clear`, `/new`) for each new task, but doing it by hand
breaks your flow.

This model makes that call on **every user turn**:

> Does this new message need the conversation so far, or could a fresh session handle it just as well?

It is a 150M-parameter [ModernBERT-base](https://huggingface.co/answerdotai/ModernBERT-base) cross-encoder. It reads
the new message together with the recent exchanges and returns `p(new_task)`. It is small enough to run locally on
every prompt, for example from a Claude Code `UserPromptSubmit` hook. This demo runs the **int8 ONNX** build on a free CPU.

**Status: v0.1 (2026-10-24), experimental.** Trained only on synthetic data and not yet checked against real sessions.
"""

HOW = f"""
## How it works

**Input.** A pair of text segments, as in training:

1. the new user message;
2. the last {MAX_TURNS} exchanges, **newest first**, each written as `AGENT: …` then `USER: …`.

The context is truncated first if the pair runs past {MAX_LEN} tokens, so the message is always read in full.

**Output.** Two logits (`continue`, `new_task`), passed through softmax to give `p(new_task)`.

**Decision.** Split only when `p(new_task) ≥ {THRESHOLD}`. The errors are not equal. A wrong split throws away the
agent's working context, while a missed split only costs some extra context. So the threshold is set for
**precision ≥ 0.95 on `new_task`** (int8 validation: precision 0.952, recall 0.921).

### Why context matters: matched pairs

The training data includes *matched pairs*: the **same message**, once in a session where it is a new task and once
in a session where it continues the work. The message alone can't separate them, so the model has to read the
context. The examples in the *Try it* tab are two such pairs from the held-out test split. Load both halves of a pair
and compare the scores.

### Training

- Data: [danielrosehill/Agent-Task-Break-Detector](https://huggingface.co/datasets/danielrosehill/Agent-Task-Break-Detector) v0.2.
  Sessions were generated by Claude Haiku 5.5 and labelled independently by Claude Sonnet 5.5. Only rows where the two
  agreed are used: 5,104 training rows, including 1,025 matched pairs.
- Categories: `far` (unrelated task), `same_workspace` (different task, same repo), `subtle_pivot`, `follow_up`,
  `implicit_reference` ("now do the same for the other one"), `hard_negative`, `counterfactual_continue`.
- 3 epochs, lr 5e-5, batch 16, bf16, on one NVIDIA L4 (6.9 minutes).
- Code: [Agent-Context-Harness](https://github.com/danielrosehill/Agent-Context-Harness), `model/train.py`.
"""

RESULTS = """
## Results (synthetic test split)

n = 608 rows, including 115 matched pairs. *Pair accuracy* counts a pair as correct only when both halves are classified correctly.

| Model | Accuracy | AUC-PR | `new_task` recall @ precision 0.95 | Pair accuracy |
|---|---|---|---|---|
| **ModernBERT, fp32** | **0.951** | **0.986** | **0.902** | **0.791** |
| ModernBERT, int8 ONNX (this demo) | 0.929 | 0.982 | 0.888 | — |
| TF-IDF, message only | 0.793 | 0.758 | 0.037 | — |
| TF-IDF, message + context | 0.760 | 0.781 | 0.140 | — |

The TF-IDF baselines are almost useless at high precision: phrasing alone doesn't tell you whether a task is new.

**Weakest categories:** `same_workspace` (0.867), a different task in the same repo, and `counterfactual_continue`
(0.896), a message that sounds self-contained but actually continues the work.

int8 probabilities run about 0.14 lower than fp32, which is why the int8 threshold (0.76) is calibrated separately.

## Limitations

- Synthetic data from a single generator. Real sessions are longer, messier and multilingual. English only.
- Training data is roughly 50/50. In real use most turns are continuations, so expect more false splits than the test set shows.
- Before you let it act unattended, pick your own threshold on your own sessions.

## Links

- Model: [danielrosehill/Agent-Task-Break-Detector-ModernBERT](https://huggingface.co/danielrosehill/Agent-Task-Break-Detector-ModernBERT)
- Dataset: [danielrosehill/Agent-Task-Break-Detector](https://huggingface.co/datasets/danielrosehill/Agent-Task-Break-Detector)
- Project and hook: [github.com/danielrosehill/Agent-Context-Harness](https://github.com/danielrosehill/Agent-Context-Harness)
"""

with gr.Blocks(title="Agent Task Break Detector", theme=gr.themes.Soft()) as demo:
    gr.Markdown(INTRO)
    with gr.Tab("Try it"):
        with gr.Row():
            with gr.Column(scale=3):
                context = gr.Textbox(
                    label="Session so far (oldest first; one USER: / AGENT: line per turn)",
                    lines=12,
                    placeholder="USER: the payments migration fails on the currency column\n"
                    "AGENT: Added a default of 'USD' in migration 0042 and re-ran it; it passes.",
                )
                message = gr.Textbox(label="New user message", lines=2)
                btn = gr.Button("Classify", variant="primary")
            with gr.Column(scale=2):
                label = gr.Label(label="Prediction", num_top_classes=2)
                verdict = gr.Markdown()
        gr.Examples(
            examples=example_rows(),
            inputs=[message, context],
            label="Matched pairs from the test split: each message appears twice, once as a new task and once as a continuation",
        )
        btn.click(classify, [message, context], [label, verdict])
        message.submit(classify, [message, context], [label, verdict])
    with gr.Tab("How it works"):
        gr.Markdown(HOW)
    with gr.Tab("Results and limits"):
        gr.Markdown(RESULTS)

if __name__ == "__main__":
    demo.launch()
