# Development plan

Derived from the 2026-10-16 voice note ([`../context/transcript-raw.txt`](../context/transcript-raw.txt))
and the prior-art findings ([`prior-art.md`](prior-art.md)). Proof-of-concept scale first.
Each phase has an exit test, and a phase that fails its test stops the plan there.

## Phase 0: Capture and prior art. **Done 2026-10-16**

- Voice note archived and transcribed.
- Prior-art scan in [`prior-art.md`](prior-art.md). Result: Claude Code Projects already does
  per-message routing to parallel threads. The open gaps are an explicit router, the tree view,
  nesting and harness-independence.

## Phase 1: Trial the incumbent (Claude Code Projects)

Goal: find out whether the built-in feature already solves the problem for Daniel.

1. Confirm that **Projects** appears in the claude.ai/code sidebar. It is a gradual rollout, with
   a waitlist otherwise.
2. Create a project on one real repo (the My Weird Prompts podcast, as in the voice note).
3. Run one flow-state session from the phone, feeding mixed tasks, follow-ups and ideas into the
   project conversation.
4. For each message, note what Projects did (`answered`, `new thread`, `routed to thread X`) and
   what Daniel wanted. Keep it in `eval/projects-trial-YYYY-MM-DD.jsonl`, in the same shape as
   the router log in [`spec.md`](spec.md) §3.4.

Exit test: if Projects' routing matches what Daniel wanted on most turns and the list view is
good enough, **stop**, write it up, and keep this repo as a usage guide. If not, the
mismatches become the eval set for phase 2.

## Phase 2: Routing eval set

1. Build 50–100 labelled turns from real transcripts plus the phase 1 log. Each item has the
   prompt, the current task, `workers[]` summaries and the gold decision.
2. Use the four labels from the spec (`continue`, `route_to_existing`, `spawn_new`, `split`),
   plus `note` if open question 4 is adopted.
3. Store under `eval/`, with transcripts redacted.

Exit test: two passes of labelling by Daniel agree with each other. If a human cannot label
consistently, a model will not either, so revisit the categories.

## Phase 3: Router prototype, offline

1. Write a single script that takes the spec §3.1 inputs as JSON and returns the spec §3.2 JSON.
2. Compare a cheap model with the frontier model, and a bare prompt with one that has cheap
   features added (time gap, cue phrases, path drift).
3. Report accuracy, confusion between `continue` and `spawn_new`, and latency against the
   30-second hook budget.

Exit test: high precision on `spawn_new` at the ≥0.80 threshold, within the latency budget.

## Phase 4: Local hook POC (Tier A)

1. Wire the router into a `UserPromptSubmit` command hook.
2. On `spawn_new`, launch `claude --bg` with the seed prompt. On `route_to_existing`, post to the
   target's messaging socket. Otherwise pass the prompt through.
3. Use it for a week and log every decision with any correction.

Exit test: Daniel prefers it to Projects for local work, or it shows a capability Projects
lacks.

## Phase 5: Tree view

Render session → thread → subagent from agent view state and the router log. Start with a TUI
or a static HTML page, before any real front end.

## Phase 6: Open harness (Tier C). Only if phases 3–5 justify it

A vendor-neutral front-end that owns the conversation and drives Claude Code, opencode or Codex
CLI workers. Decide then whether this becomes its own repo.

## Not doing

- Replacing compaction. Workers still compact. The router only delays the need for it.
- Building a parallel-session manager. Claude Squad, Crystal/Nimbalyst, Vibe Kanban and agent
  view already cover that.

## Update 2026-10-24: local-classifier track

A second track runs alongside phases 1–6, and doesn't wait on the Projects trial. Projects is
cloud-only, and this track replaces the manual `/clear` in the **local CLI**.

- **L0. Done 2026-10-24.** Prior-art update ([`prior-art-2026-10-24.md`](prior-art-2026-10-24.md)):
  the gap is open. Hook draft with a Haiku teacher backend ([`../hooks/new-task-split/`](../hooks/new-task-split/)).
- **L1.** Test the terminal transport end to end in a throwaway tmux session: block, `/clear`,
  re-send, SessionStart notice, undo.
- **L2.** Gold eval set from Daniel's own transcripts (this replaces phase 2's labels with the
  binary `continue` / `new_task`).
- **L3.** Teacher labelling and synthetic splices, batched. **Synthetic part done 2026-10-24:**
  public dataset [Agent-Task-Break-Detector](https://huggingface.co/datasets/danielrosehill/Agent-Task-Break-Detector) v0.1 (986 scenarios, 5,916 rows, 86.6%
  generator/verifier agreement, US$2.38), built by [`../dataset/`](../dataset/). Teacher labels on
  real transcripts are still to do, and stay private.
- **L4.** Fine-tune ModernBERT-base or Ettin-150M, export int8 ONNX, benchmark latency.
- **L5.** Swap the hook's backend to the local model and run it for a week, logging undos.

Details and exit tests are in [`local-classifier-plan.md`](local-classifier-plan.md).

