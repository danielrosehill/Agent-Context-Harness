# Plan: local "new session?" classifier

Status: **plan, 2026-10-24.** Nothing trained yet. Source: the 2026-10-24 voice note and the
follow-up conversation. Prior art: [`prior-art-2026-10-24.md`](prior-art-2026-10-24.md).

## Why local

Decided by Daniel on 2026-10-24: **an API call on every turn doesn't make sense**, however cheap.
Measured on 2026-10-24 with the hook draft in [`../hooks/new-task-split/`](../hooks/new-task-split/)
and Claude Haiku 5.5:

| Cost | Measured |
|---|---|
| Tokens per classified turn | ~670 in, ~50 out (about $0.0001 at $0.10/$0.50 per MTok) |
| Wall time per classified turn | **3–5 s**: ~2 s importing the `anthropic` SDK, ~1.4 s for `with-secrets` (Infisical) to fetch the key, ~1 s for the API call |
| Accuracy on 4 synthetic cases | 4/4 (2 continuations, 2 new tasks) |

Money is negligible, but the delay lands on **every prompt**, because `UserPromptSubmit` blocks
until the hook returns. A local model answers in well under a second, needs no key and no network,
keeps prompts on the machine, and is **portable to other agent harnesses**: the artefact is a
model file plus a tiny CLI, not a Claude-specific API integration.

## The task

Binary, per user turn:

- **input**: the new user message, plus the last few user messages and the tail of the agent's
  last reply (tool output stripped), capped at 512–1024 tokens
- **output**: `continue` or `new_task`, with a probability

`new_task` means: the message starts work a fresh agent could do as well as this one, with no
reference back to the conversation. Same repo is not the same task.

The asymmetry from [`spec.md`](spec.md) §3.3 stands: a wrong `new_task` throws away working
context, a wrong `continue` costs some extra context. Tune for **precision on `new_task`**
(target ≥ 0.95 at the operating threshold) and accept lower recall.

## Model

- **Base**: ModernBERT-base (149M, Apache-2.0, 8k context) or the Ettin-150M encoder, as a
  cross-encoder: `new message [SEP] recent context`.
- **Export**: int8 ONNX, run with onnxruntime on CPU.
- **Latency target**: under 200 ms on the laptop at 512 tokens, including process start.
  Unbenchmarked: measure early. If it misses, distil into Ettin-68M or MiniLM-L12 (33M).
- Same pattern as the Gemma 270M + ONNX paragraph-break model (see the ASR paragraph-breaks
  repo), so the training and export tooling can be reused.

## Data

1. **Teacher labels on real coding sessions.** Daniel's own `~/.claude/projects/**/*.jsonl`
   transcripts, plus public Claude Code trace sets (licences to check: see the prior-art doc).
   For each user turn, a frontier model labels `continue` / `new_task` with a confidence.
   Batch it (`batch-jobs` plugin), never per-turn.
2. **Synthetic splices.** Join the opening of session B onto the middle of an unrelated session A
   to make hard, guaranteed `new_task` positives. Splice within the **same repo** too, so the
   model can't learn "different repo name = new task".
3. **Hard negatives.** Topic-looking follow-ups ("separate question about the cache you just
   added", "also fix the tests") labelled `continue`.
4. **Gold eval set.** 150–300 turns from Daniel's own sessions, labelled by Daniel. Never used
   for training. This is phase 2 of [`development-plan.md`](development-plan.md), now aimed at
   the local model.
5. **Live corrections.** Once the hook runs, every **undo** (a split message brought back to the
   old session) and every `same:` prefix is a gold "wrong split" label. The hook already logs
   these to `~/.cache/new-task-split/decisions.jsonl`.

**Synthetic set, v0.1 (2026-10-24):** [https://huggingface.co/datasets/danielrosehill/Agent-Task-Break-Detector](https://huggingface.co/datasets/danielrosehill/Agent-Task-Break-Detector). Haiku 5.5 writes agent sessions of seven
kinds (half coding) with six candidate next messages each (follow_up, hard_negative,
implicit_reference → continue; same_workspace, subtle_pivot, far → new_task), and Sonnet 5.5
re-labels them blind. Train on `agreed == true`. `subtle_pivot` is the noisy slot (53%
disagreement). Scripts and card: [`../dataset/`](../dataset/).

Exclude Hebrew/RTL and redact before anything leaves the machine. Transcripts are private: the
dataset stays private unless it is fully synthetic.

## Harness integration (portable by design)

One CLI, `new-task-classify`, reads a small JSON envelope (`prompt`, `recent_user[]`,
`last_reply`) on stdin and prints `{decision, p}`. Each harness gets a thin adapter:

| Harness | Adapter |
|---|---|
| Claude Code | `UserPromptSubmit` command hook: [`../hooks/new-task-split/`](../hooks/new-task-split/) |
| opencode, Codex CLI, others | Their own pre-prompt hook or plugin point. To survey when the model works |

Acting on the decision is harness-specific. In Claude Code no hook can run `/clear`, so the
draft blocks the prompt and drives the terminal (Konsole D-Bus or tmux) to type `/clear` and
re-send the message. That transport is untested: see the hook README.

## Exit tests

1. **Data**: Daniel's two labelling passes on the gold set agree (from development-plan phase 2).
2. **Model**: on the gold set, precision on `new_task` ≥ 0.95 at a threshold where recall is
   still useful (≥ 0.5), and p95 latency under 200 ms on the laptop.
3. **Use**: a week with the hook on, with the undo rate logged. If Daniel undoes more than about
   1 split in 10, the threshold or the model is wrong.

## Open questions

1. Is `continue` vs `new_task` enough, or does the local model also need `route_to_existing`
   (spec §2)? Start binary: it is the decision Daniel makes by hand today.
2. How much context does the model need? Test the last 1, 2 and 4 user turns.
3. Does the agent's last reply help, or does it just add noise? Ablate it.
