# Agent Context Harness

**Status:** idea and research, opened 2026-10-16. Since 2026-10-24 there is also a local-CLI track: a draft split hook ([`hooks/new-task-split/`](hooks/new-task-split/)) and a plan to train a **local classifier** for it ([`docs/local-classifier-plan.md`](docs/local-classifier-plan.md)).

When you work with a coding agent in a flow state, you keep dropping new, unrelated tasks into
the same thread: a bug, then an idea, then another fix. That history piles up and degrades the
agent's context long before the window is full. The hygienic fix is a fresh session per task,
but starting sessions by hand breaks the flow.

The idea is a **per-turn router**. On every message, a classifier decides whether the message is:

- a continuation of the current task,
- a continuation of a task a worker already owns, or
- a new task.

A new task spawns a **parallel orchestrator instance**: a full new agent session on its own
branch or worktree, not a subagent. That instance can delegate to its own subagents. One manager
view shows the whole tree:

```
session → parallel threads → subagents
```

The aim is to keep each thread clean so compaction is rarely needed, rather than repairing
context once it has gone bad.

## Prior-art verdict (2026-10-16)

Claude Code **Projects** (public beta, Pro and Max plans) already does the core of this. One
coordinating conversation starts threads, or routes a message to the thread already working in
that area, and each thread is a separate session on its own branch.

What remains open:

- an explicit, inspectable routing classifier with a confidence score and an eval set
- the session → thread → subagent tree view
- nesting
- a vendor-neutral harness

See [`docs/prior-art.md`](docs/prior-art.md).

## Contents

| Path | What |
|---|---|
| [`context/voice-note.mp3`](context/voice-note.mp3) | Original development-plan voice note, about 12 MB |
| [`context/transcript-raw.txt`](context/transcript-raw.txt) | Raw transcript (AssemblyAI universal, 2026-10-16). Kept as is |
| [`docs/prior-art.md`](docs/prior-art.md) | Prior-art scan with sources, confidence levels and verdict |
| [`docs/spec.md`](docs/spec.md) | Draft spec: routing decision, hook points, spawning, tree model, open questions |
| [`docs/development-plan.md`](docs/development-plan.md) | Phased plan, POC first |
| [`context/2026-10-24_auto-session-hook-transcript-raw.txt`](context/2026-10-24_auto-session-hook-transcript-raw.txt) | Raw transcript of the second voice note, about a local `/clear`-replacing hook (AssemblyAI universal, 2026-10-24). Audio not archived |
| [`docs/prior-art-2026-10-24.md`](docs/prior-art-2026-10-24.md) | Prior-art update: no harness or released model decides "new session vs continue" per turn |
| [`docs/local-classifier-plan.md`](docs/local-classifier-plan.md) | Plan for a small local ONNX classifier: data, model, exit tests |
| [`dataset/`](dataset/) | Scripts and card for the public synthetic training set [Agent-Task-Break-Detector](https://huggingface.co/datasets/danielrosehill/Agent-Task-Break-Detector) |
| [`hooks/new-task-split/`](hooks/new-task-split/) | Draft Claude Code hook: blocks an unrelated prompt, runs `/clear`, re-sends it |
| [`space/`](space/) | Source of the Hugging Face Space [Agent-Task-Break-Detector](https://huggingface.co/spaces/danielrosehill/Agent-Task-Break-Detector): explainer plus live int8 ONNX demo. Deploy: `hf upload danielrosehill/Agent-Task-Break-Detector space . --repo-type space --exclude "__pycache__/*"` |
| [`project.json`](project.json) | Machine-readable summary |

## Related

- [Claude-Air-Traffic-Control](https://github.com/danielrosehill/Claude-Air-Traffic-Control):
  routing the operator's *attention* across many sessions. This repo routes the *work*.
- [Claude-Fleet-Traffic-Shaper](https://github.com/danielrosehill/Claude-Fleet-Traffic-Shaper)
- [Claude-Tooling-Prior-Art](https://github.com/danielrosehill/Claude-Tooling-Prior-Art)

There are no Hugging Face resources for this project. Daniel's full Hugging Face listing was
checked on 2026-10-16.
