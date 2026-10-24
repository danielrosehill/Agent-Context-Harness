# new-task-split (draft Claude Code hook)

Status: **draft, 2026-10-24. Not installed anywhere.**

It works on a `UserPromptSubmit` hook. When a message looks like an unrelated new task, the hook
blocks it in the current session, runs `/clear`, and re-sends the message into the fresh session.
The old session stays in `/resume`.

## Why it drives the terminal

On Claude Code 2.1.310, no hook output can run `/clear`, start a session or rewrite the prompt
(see [`../../docs/prior-art-2026-10-24.md`](../../docs/prior-art-2026-10-24.md) §1). So after
blocking, a detached helper types into the terminal the session runs in:

| Transport | When | How |
|---|---|---|
| `konsole` | `KONSOLE_DBUS_SERVICE` and `KONSOLE_DBUS_SESSION` set, `qdbus` present | `org.kde.konsole.Session.sendText` |
| `tmux` | `TMUX_PANE` set | `tmux send-keys -l` |
| `clipboard` | anything else | `wl-copy`, and the block message asks you to `/clear` and paste |

The helper sends `/clear`, then the message. Multi-line messages go in as a bracketed paste.
Timing is set with `NEW_TASK_SPLIT_DELAY` (default 1.0 s) and `NEW_TASK_SPLIT_CLEAR_WAIT`
(default 2.0 s).

## Controls

| Input | Effect |
|---|---|
| `same: …` or `here: …` | Never split this message |
| `new: …` or `split: …` | Split without classifying |
| `split off` / `split on` | Turn off or on for this session |
| `NEW_TASK_SPLIT=off` | Turn off everywhere |
| Undo | `/resume`, pick the old session, re-send. A message split in the last 30 minutes is recognised and kept |

A `SessionStart` hook (`source: clear`) tells the fresh session it was auto-split and how to undo,
so "you got that wrong" gets a useful answer.

## Skipped without classifying

Slash commands, `!` shell lines, machine-sent turns starting with `<` (task notifications, peer
messages), messages under 40 characters, and sessions with fewer than 2 earlier prompts.

## Classifier backend

The draft calls **Claude Haiku 5.5** with structured JSON output. On 2026-10-24 that call got 4/4
synthetic cases right at about $0.0001 a turn, but took **3–5 s a turn**. So the plan is a local
model ([`../../docs/local-classifier-plan.md`](../../docs/local-classifier-plan.md)), and the
Haiku path stays only as the **teacher** for labelling training data. It needs `ANTHROPIC_API_KEY`
in the environment. With no key, the hook logs `skipped_no_key` and lets the prompt through.

Every decision, error and skip is logged to `~/.cache/new-task-split/decisions.jsonl`
(`NEW_TASK_SPLIT_STATE` overrides the directory).

## Tested

- Classifier decisions: 4 synthetic cases, all correct (2026-10-24).
- Block JSON and the clipboard fallback message: checked by hand.
- **Not tested**: the Konsole and tmux transports, the `/clear` → re-send sequence, the
  SessionStart notice, and the undo detection end to end.

## Wiring (when ready)

The Haiku backend needs the `anthropic` package: `uv venv .venv && uv pip install --python .venv/bin/python anthropic` in this folder.

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command",
      "command": "~/repos/github/ai-agents-and-prompts/Agent-Context-Harness/hooks/new-task-split/.venv/bin/python ~/repos/github/ai-agents-and-prompts/Agent-Context-Harness/hooks/new-task-split/new_task_split.py",
      "timeout": 15 }] }],
    "SessionStart": [{ "matcher": "clear", "hooks": [{ "type": "command",
      "command": "python3 ~/repos/github/ai-agents-and-prompts/Agent-Context-Harness/hooks/new-task-split/new_task_split.py" }] }]
  }
}
```
