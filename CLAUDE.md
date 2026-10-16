# Agent-Context-Harness: agent notes

## Purpose

This is the research repo for a per-turn task router. On each user message it decides between
`continue`, `route_to_existing`, `spawn_new` and `split`. New tasks go to parallel full agent
sessions, not subagents, so that each thread's context stays clean.

## Status (2026-10-16)

- Idea and research only. There is no code.
- The prior-art scan is done, in `docs/prior-art.md`. Its main finding: Claude Code Projects
  already does per-message routing to parallel cloud threads.

## Layout

- `context/voice-note.mp3`: the source voice note.
- `context/transcript-raw.txt`: its raw transcript (AssemblyAI universal).
- `docs/prior-art.md`: what exists, with links and confirmed or inferred tags.
- `docs/spec.md`: the draft spec. Items are tagged [D] (Daniel), [P] (agent proposal) or [PA]
  (shaped by prior art). It ends with a decision log.
- `docs/development-plan.md`: phases 0–6, each with an exit test.
- `project.json`: machine-readable summary. Keep `status` and `next_step` current.
- `eval/`: does not exist yet. Phase 1 and 2 data goes here, redacted.

## Conventions

- `context/transcript-raw.txt` is **immutable**. Do not correct ASR errors in it (for example
  "Claus"/"plaud" for Claude, "wordprompts" for Weird Prompts). If a cleaned version is needed,
  write it to a separate file.
- Keep the provenance tags in `docs/spec.md`. When something is decided, add a dated entry to
  its Decision log saying what settled it. Do not silently rewrite earlier sections.
- Date every prior-art claim and mark it as confirmed, secondary or inferred. Re-verify before
  relying on anything older than about a month, because this area changes quickly.

## Next step

Phase 1 of `docs/development-plan.md`: trial Claude Code Projects on a real repo from the phone,
and log every routing decision against what Daniel wanted. Build nothing until that trial shows
a gap.
