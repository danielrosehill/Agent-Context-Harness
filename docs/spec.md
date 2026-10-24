# Draft spec: per-turn task router

Status: **draft, 2026-10-16.** Nothing here is built.

Provenance tags:

- **[D]**: from Daniel's voice note ([`../context/transcript-raw.txt`](../context/transcript-raw.txt)).
- **[P]**: proposed by the agent that wrote this draft. Open to change.
- **[PA]**: shaped by something found in [`prior-art.md`](prior-art.md).

Record decisions in the Decision log at the bottom. Do not silently edit the sections above it.

## 1. Problem

- **[D]** In a flow state, a user drops several unrelated tasks into one Claude Code thread. On
  mobile and web each session is one repo and branch in an ephemeral container. The thread fills
  with unrelated history, and context quality degrades well before the window is full.
- **[D]** Starting a new session for each task by hand is the hygienic fix, but users do not
  want to make that choice deterministically. They want one manager conversation.
- **[D]** Compaction is a retrospective repair at the point of failure. The goal is to avoid
  reaching it, by threading work out early.
- **[PA]** Evidence that this matters: Chroma's LongMemEval result (focused prompts of about 300
  tokens beat full histories of about 113k tokens across all model families).

## 2. Core concept

- **[D]** On every user turn, a classifier decides whether the message is:
  1. a continuation of the current task,
  2. a continuation of a task a worker already owns, or
  3. a new task.
- **[D]** A new task spawns a **parallel orchestrator instance**: a new Claude process and
  thread, *not* a subagent. That instance can delegate to its own subagents, just like the main
  orchestrator.
- **[D]** Orchestration is parallelised rather than nested. Subagent delegation happens inside
  each parallel instance.
- **[D]** The router could be a hook, an accessory model, or part of an open-source harness.
  Probably bigger than Claude.

## 3. The routing decision

### 3.1 Inputs  [P]

| Field | Source | Notes |
|---|---|---|
| `prompt` | `UserPromptSubmit` input | Full text, with pasted text expanded |
| `current_task` | Router state | Title, one-line goal and touched paths of the thread receiving the message |
| `workers[]` | Router state, refreshed from `ListAgents` / agent view | For each: `id`, `title`, `goal`, `status`, `touched_paths[]`, `last_summary` |
| `recent_turns` | `transcript_path` | Last N user and assistant turns of the receiving thread, not the full history |
| `signals` | Cheap features | Time since last turn, structural cue phrases ("also", "different thing", "while I think of it"), file-path drift as in topic-switch |

The router must never read the whole transcript. Its cost has to stay flat as the session
grows. **[P]**

### 3.2 Output  [P]

JSON only:

```json
{
  "decision": "continue | route_to_existing | spawn_new | split",
  "confidence": 0.0,
  "target_worker_id": "string, only for route_to_existing",
  "new_tasks": [
    {
      "title": "short imperative title",
      "goal": "one sentence",
      "seed_prompt": "self-contained brief for the new instance",
      "likely_paths": ["src/..."]
    }
  ],
  "rationale": "one sentence, logged, never shown to the worker"
}
```

- `split` covers a single message that holds several unrelated tasks. Projects does the same
  ("Several unrelated tasks in one message become separate threads"). **[PA]**
- `seed_prompt` follows Amp Handoff's approach: extract what the new task needs, rather than
  summarising everything. **[PA]**

### 3.3 Thresholds  [P], [PA] from Pantheon

| Confidence | Action |
|---|---|
| ≥ 0.80 | Act automatically, and tell the user in one line which worker got the message |
| 0.50 – 0.80 | Propose. The user confirms with one tap or word |
| < 0.50 | Default to `continue` |

The asymmetry is deliberate. A wrong `spawn_new` costs a cold start and a lost thread of
reasoning, while a wrong `continue` costs some context pollution. So the system should be
conservative about spawning until the eval says otherwise. **[P]**

### 3.4 Logging  [P]

Every decision is appended to `router-log.jsonl` with the inputs digest, the output and the
user's correction, if any. User corrections are the labelled data for the eval in phase 2 of
the development plan.

## 4. Where it hooks in

Three tiers, from cheapest to most complete. **[P]**

### Tier A: Claude Code hook (local CLI)

- `UserPromptSubmit` with `type: "prompt"` or `type: "command"`. Both are supported on this
  event (confirmed in the hooks docs, 2026-10-16).
- `continue`: exit 0 with no output.
- `spawn_new`: the hook runs `claude --bg "<seed_prompt>"` (agent view puts it in its own
  worktree), then returns `decision: "block"` with a `reason` such as "Started background
  session 'fix RSS feed'". The original thread stays clean.
- `route_to_existing`: the hook writes the prompt to the target session's inbox socket (each
  session exports `CLAUDE_CODE_MESSAGING_SOCKET`; other sessions are discovered with
  `ListAgents` or `/list-agents`), then blocks locally with a pointer.
- Constraints: the event's default timeout is 30 seconds. A hook cannot rewrite the prompt,
  only block it or add context. A prompt-type hook returns `{ok, reason}`, so it cannot carry
  the full JSON above. The hook therefore probably needs to be a command hook that calls a
  model itself.
- Unverified: whether a hook process can launch `claude --bg` sessions reliably, given
  permissions, the supervisor and the environment.

### Tier B: Claude Code Projects (cloud and mobile)

- Projects already routes. Here the work is **tuning it rather than replacing it**: project
  instructions that spell out the routing policy (when to spawn, when to reuse), plus
  observation of where its routing differs from what Daniel wanted.
- A hook cannot be inserted into the Projects coordinator, as far as the docs say. Treat this
  tier as the baseline the custom router has to beat.

### Tier C: Open harness  [D] "bigger than Claude"

- A thin front-end process owns the conversation, runs the router, and drives worker sessions
  through each agent CLI's headless or background mode: `claude --bg` or `-p`, opencode, Codex
  CLI.
- This is the only tier that gives an explicit tree, nesting and vendor independence.

## 5. Spawning and deconfliction

- **[D]** Rely on branch hygiene. Each worker gets its own branch.
- **[P]** Each worker gets its own git worktree. Agent view already does this, under
  `.claude/worktrees/`. In the cloud, a thread gets its own container and branch.
- **[P]** Overlap check at spawn time: if `likely_paths` intersects a live worker's
  `touched_paths`, prefer `route_to_existing`, or tell the user about the overlap.
- **[P]** Seeding: the new worker gets `seed_prompt` plus the repo's normal baseline (CLAUDE.md,
  memory). Daniel already relies on these to preserve baseline context. **[D]**
- **[P]** Teardown: a worker finishes with a PR or a summary, and the router marks it idle.
  Idle workers stay routable for follow-ups.

## 6. Visual model  [D]

```
Session: "Morning MWP sprint"            ← one conversation, the manager
├── Thread: fix RSS feed                 ← parallel orchestrator instance
│   ├── subagent: Explore
│   └── subagent: test-runner
├── Thread: new episode-page layout
│   └── subagent: copywriter
│       └── subagent: SEO                ← how deep can this go? (open question)
└── Thread: idea, voice-note intake
```

- **[D]** Shaped like a VS Code file tree, with expandable nodes for recursive delegation.
- **[P]** Each node shows state (working, waiting on you, ready for review, idle), its branch or
  PR, and a one-line last summary.
- **[PA]** No product found renders this tree. Projects and agent view group by state, and
  opencode only offers parent/child navigation.

## 7. Open questions

1. **[D]** How deep can delegation recurse? Confirmed constraint: agent teams disallow nested
   teams. Subagent nesting depth in Claude Code is unverified.
2. **[D]** Is a per-turn hook enough on its own, or does the front end need to change for the
   behaviour to be visible?
3. **[P]** Can a small or cheap model route accurately enough, or does it need the frontier
   model plus `workers[]` summaries?
4. **[P]** How should "thinking out loud" turns (ideas, not tasks) be handled? Possibly a
   fourth decision, `note`, that files the idea without spawning.
5. **[P]** Cost: parallel sessions draw on plan limits faster (stated in both the Projects and
   agent view docs). Should the router enforce a concurrency cap?
6. **[PA]** Does Projects' built-in routing already meet Daniel's need? This needs a real trial
   before any building.

## Decision log

Append one entry per decision: date, decision, what settled it.

- 2026-10-16: Repo opened as idea and research. Prior-art scan done before any design work, at
  Daniel's request in the voice note.
- 2026-10-24: Second voice note
  ([`../context/2026-10-24_auto-session-hook-transcript-raw.txt`](../context/2026-10-24_auto-session-hook-transcript-raw.txt))
  narrows a track to the **local CLI, in place**: replace the manual `/clear` / `/new` Daniel already
  does, rather than spawning a parallel `--bg` worker. Requirements from it: a visible notice when a
  split happens, undo through session history (`/resume`), and a way to tell it "you got that wrong"
  so it doesn't repeat. Projects (phase 1) doesn't cover this, because it is cloud-only.
- 2026-10-24: Hooks can't run `/clear` or swap sessions (hooks docs, v2.1.310), so the in-place
  version blocks the prompt and drives the terminal (Konsole D-Bus or tmux) to `/clear` and re-send.
  Draft in [`../hooks/new-task-split/`](../hooks/new-task-split/). Transport untested.
- 2026-10-24: **The classifier will be a local model, not an API call per turn.** Daniel's decision,
  after measuring the Haiku 5.5 hook draft: about $0.0001 a turn, but 3–5 s of blocking latency on
  every prompt. A local model is also portable to other harnesses. The prior-art update
  ([`prior-art-2026-10-24.md`](prior-art-2026-10-24.md)) found no built-in, harness or released
  model doing this. Claude Code's only related feature is a time-based idle-return `/clear` hint
  (75+ min idle, since v2.1.92). Plan: [`local-classifier-plan.md`](local-classifier-plan.md). The
  Haiku path is kept only as a teacher for labelling.

