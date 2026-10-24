# Agent-Context-Harness: agent notes

## Purpose

This is the research repo for a per-turn task router. On each user message it decides between
`continue`, `route_to_existing`, `spawn_new` and `split`. New tasks go to parallel full agent
sessions, not subagents, so that each thread's context stays clean.

## Status (2026-10-24)

- Two tracks. (1) The original router idea: research only. Claude Code Projects already does
  per-message routing to parallel cloud threads (`docs/prior-art.md`). (2) Since 2026-10-24, a
  **local-CLI split hook** with a **local classifier model**. The draft hook is in
  `hooks/new-task-split/`, the prior art in `docs/prior-art-2026-10-24.md` (gap open), and the
  plan in `docs/local-classifier-plan.md`.
- No per-turn API calls in the final design: Daniel's decision, 2026-10-24. The Haiku backend in
  the hook is only a teacher for labelling data.

## Layout

- `context/voice-note.mp3`: the source voice note.
- `context/transcript-raw.txt`: its raw transcript (AssemblyAI universal).
- `context/2026-10-24_auto-session-hook-transcript-raw.txt`: raw transcript of the second voice
  note (AssemblyAI universal). Immutable like the first. The MP3 was deliberately not added.
- `dataset/`: generator for the public HF dataset `danielrosehill/Agent-Task-Break-Detector`
  (https://huggingface.co/datasets/danielrosehill/Agent-Task-Break-Detector). `scripts/make_requests.py` → `anthropic_batch.py` (Haiku) → `verify_requests.py` →
  `anthropic_batch.py --model claude-sonnet-5-5` → `build_dataset.py … hf`, then `hf upload`.
  `raw/` and `hf/data/` are gitignored; the data lives on the Hub. Fully synthetic only: never add
  Daniel's transcripts to it.
- `hooks/new-task-split/`: draft `UserPromptSubmit` + `SessionStart` hook and its README.
- `docs/prior-art-2026-10-24.md`, `docs/local-classifier-plan.md`: the local-classifier track.
- `docs/prior-art.md`: what exists, with links and confirmed or inferred tags.
- `docs/spec.md`: the draft spec. Items are tagged [D] (Daniel), [P] (agent proposal) or [PA]
  (shaped by prior art). It ends with a decision log.
- `docs/development-plan.md`: phases 0–6, each with an exit test.
- `model/`: `baseline.py`, `train.py` (HF Trainer cross-encoder), `common.py`. `model/data/` (v0.2 JSONL) is gitignored.
- `docs/eval-plan.md`: pass bar, baselines, every training run.
- `project.json`: machine-readable summary. Keep `status` and `next_step` current.
- `eval/`: does not exist yet. Phase 1 and 2 data goes here, redacted.

## Conventions

- `context/*transcript-raw.txt` files are **immutable**. Do not correct ASR errors in it (for example
  "Claus"/"plaud" for Claude, "wordprompts" for Weird Prompts). If a cleaned version is needed,
  write it to a separate file.
- Keep the provenance tags in `docs/spec.md`. When something is decided, add a dated entry to
  its Decision log saying what settled it. Do not silently rewrite earlier sections.
- Date every prior-art claim and mark it as confirmed, secondary or inferred. Re-verify before
  relying on anything older than about a month, because this area changes quickly.

## Next step

Synthetic dataset v0.1 is published (L3, synthetic part) and L1 (tmux end to end) passed on
2026-10-24. v0.2 (counterfactual pairs, built locally by `dataset/scripts/add_counterfactuals.py`,
not yet on the Hub) trained ModernBERT-base on Modal: runs and numbers in `docs/eval-plan.md`,
code in `model/`. Next: ONNX int8 export and latency bench, publish v0.2, then L2, the gold eval
set from Daniel's transcripts. Test hook
changes only in a throwaway tmux session started from the scratch project, never by triggering a
split in a live session: the transport types into real terminals. The Projects trial (phase 1) still stands
for the cloud/mobile router idea.
