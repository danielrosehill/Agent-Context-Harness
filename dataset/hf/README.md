---
license: cc-by-4.0
language:
- en
pretty_name: Agent Task Break Detector
size_categories:
- 1K<n<10K
task_categories:
- text-classification
tags:
- agents
- ai-agents
- context-management
- topic-shift
- dialogue
- synthetic
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.jsonl
  - split: validation
    path: data/validation.jsonl
  - split: test
    path: data/test.jsonl
---

# Agent Task Break Detector

Synthetic training data for a small classifier that answers one question on every user turn
of an AI agent session:

> **Does this new message need the conversation so far, or is it a new task that a fresh
> session could handle just as well?**

Agent sessions build up context. When a user drops an unrelated task into a long session, the
old history only gets in the way, so the clean move is a fresh session: `/clear` or `/new` in
Claude Code, a new thread elsewhere. Today people make that call by hand. A classifier that makes
it automatically has to run on **every** turn, so it should be small and local, not an API call.
This dataset is for training that classifier.

It isn't tied to any one harness. About half the sessions are coding agents in a repository. The
rest are research, sysadmin, writing, data-analysis, personal-assistant and browser-automation
agents.

**Status: v0.1, 2026-10-24.** Fully synthetic, with machine-generated and machine-verified labels.
Nothing has been trained on it yet. It is not a human-labelled benchmark.

## Labels

| `label` | Meaning |
|---|---|
| `continue` | The message needs or builds on the conversation: a follow-up, correction, approval, question about what was just done, extension of it, or an explicit or implicit reference back |
| `new_task` | A fresh agent with no memory of the conversation could do it just as well. Being in the **same repository or workspace does not make it the same task** |

Each scenario has six candidate next messages, one of each `kind`:

| `kind` | `label` by design | Why it's there |
|---|---|---|
| `follow_up` | continue | The easy case |
| `hard_negative` | continue | Sounds like a topic change ("btw", "different thing", "quick one") but depends on the conversation |
| `implicit_reference` | continue | Refers back only through pronouns or "the other one", "same for the tests" |
| `same_workspace` | new_task | A different task in the same repo or domain |
| `subtle_pivot` | new_task | Shares vocabulary with the session but is independent work, with no topic-change marker |
| `far` | new_task | Clearly unrelated |

The generator may label a candidate differently from its slot when it judges that right, so check
`label`, not `kind`.

## Fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | `<scenario_id>-<candidate index>` |
| `scenario_id` | string | The six rows of a scenario share their context |
| `agent_kind`, `domain`, `task`, `user_style` | string | The seed the scenario was generated from. `task` is null outside coding scenarios |
| `workspace` | string | One-line description of the repo or workspace |
| `context` | list of `{user, agent}` | 2–5 earlier exchanges. Agent turns are short summaries, like the tail of a real reply, with no raw tool output |
| `message` | string | The candidate next user message |
| `label` | `continue` \| `new_task` | The generator's intended label |
| `kind` | string | See above |
| `rationale` | string | The generator's reason, under 15 words |
| `verifier_label` | `continue` \| `new_task` \| `ambiguous` | Blind label from a second, stronger model |
| `verifier_confidence` | float | 0–1 |
| `agreed` | bool | `label == verifier_label` |
| `generator_model`, `verifier_model` | string | `claude-haiku-5-5`, `claude-sonnet-5-5` |

**For training, filter to `agreed == true`.** Disagreements are kept because they're informative:
in the pilot, nearly all of them were real borderline cases (the verifier said `ambiguous`), not
generator mistakes.

## How it was made

1. **Seeds.** Each scenario samples an agent kind, a domain, for coding a current task, one of
   eight user styles (terse, dictated by voice with self-corrections, non-native, vague, …) and a
   session length. Script: `make_requests.py`.
2. **Generation.** Claude Haiku 5.5 on the Anthropic Message Batches API writes the session and
   the six candidates under a JSON schema. Its prompt includes anti-shortcut rules: varied
   topic-change phrases, most `new_task` messages with no signal phrase, and lengths from 3 to 80
   words.
3. **Blind verification.** Claude Sonnet 5.5 sees the conversation and the six candidates without
   the intended labels, and labels each one `continue`, `new_task` or `ambiguous` with a
   confidence. Script: `verify_requests.py`.
4. **Build.** Rows are flattened and split **by scenario** (a hash of `scenario_id`, 80/10/10), so
   no context appears in two splits. Script: `build_dataset.py`.

The scripts live in [danielrosehill/Agent-Context-Harness](https://github.com/danielrosehill/Agent-Context-Harness)
under `dataset/scripts/`.

## Stats (v0.1)

1,000 scenarios generated; 14 dropped (generator returned other than six candidates). **986
scenarios, 5,916 rows**: train 4,698 / validation 648 / test 570. Intended labels: 2,960
`continue`, 2,956 `new_task`. About half the scenarios (517) are coding agents.

Generator and verifier agreed on **5,125 rows (86.6%)**. Of the 791 disagreements the verifier said
`ambiguous` 664 times, `continue` 115 and `new_task` 12. By kind (agreed / disagreed):

| `kind` | agreed | disagreed |
|---|---|---|
| `follow_up` | 970 | 16 |
| `hard_negative` | 941 | 45 |
| `implicit_reference` | 934 | 52 |
| `same_workspace` | 848 | 138 |
| `subtle_pivot` | 466 | **520** |
| `far` | 966 | 20 |

`subtle_pivot` is the hard slot: more than half the time the verifier judged it not clearly
independent. After filtering to `agreed`, the set is 2,847 `continue` / 2,278 `new_task`.

Cost: US$2.38 on the Anthropic Message Batches API (Haiku 5.5 generation $0.34, Sonnet 5.5
verification $2.00, pilot $0.05).

## Known limitations

- **Synthetic.** Real sessions are messier: longer, with tool output, pasted logs and typos.
  Treat this as a pretraining set and evaluate on real, hand-labelled sessions.
- **Balance by design.** Rows are about 50/50 `continue`/`new_task`. In real use most turns are
  continuations, so calibrate the threshold on real data.
- **One-generator style.** All sessions come from one model, so phrasing is more uniform than in
  the wild.
- **English only.**
- **Labels are model judgments.** There is no human review in v0.1.

## Intended use

Fine-tuning a small encoder (for example ModernBERT-base or a 30–150M-parameter model) as a
cross-encoder over `message [SEP] recent context`, exported to ONNX for on-device, per-turn use
inside an agent harness hook. The intended operating point is **high precision on `new_task`**: a
wrong split throws away the agent's working context, while a missed split only costs some extra
context.

## Licence

CC BY 4.0.
