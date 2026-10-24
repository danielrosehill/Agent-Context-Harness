# new-task-split (draft Claude Code hook)

Status: **draft, 2026-10-24. Not installed anywhere.** The tmux path passed an end-to-end test on
2026-10-24 (see Tested).

It works on a `UserPromptSubmit` hook. When a message looks like an unrelated new task, the hook
blocks it in the current session, runs `/clear`, and re-sends the message into the fresh session.
The old session stays in `/resume`.

## Why it drives the terminal

On Claude Code 2.1.310, no hook output can run `/clear`, start a session or rewrite the prompt
(see [`../../docs/prior-art-2026-10-24.md`](../../docs/prior-art-2026-10-24.md) §1). So after
blocking, a detached helper types into the terminal the session runs in:

| Transport | When | How |
|---|---|---|
| `tmux` | `TMUX_PANE` set, and the pane's `#{pane_pid}` is an ancestor of the hook | `tmux send-keys -l` |
| `konsole` | `KONSOLE_DBUS_SERVICE` and `KONSOLE_DBUS_SESSION` set, and the session's `foregroundProcessId` is an ancestor of the hook | `qdbus6 … org.kde.konsole.Session.sendText` |
| `clipboard` | anything else | `wl-copy`, and the block message asks you to `/clear` and paste |

Candidates are tried innermost first (tmux, then Konsole). Each is used **only if its process is an
ancestor of the hook**, because terminal env vars leak into nested terminals; otherwise the hook
falls back to the clipboard. The helper empties the input box (Ctrl+U and Backspace per line),
sends `/clear`, then the message (without any `new:`/`split:` prefix). Multi-line messages go in as a bracketed paste.
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
- **End to end in tmux, 2026-10-24** (Claude Code 2.1.310, Haiku session, scratch project with the
  hook in `.claude/settings.json`, tmux launched from Konsole so the Konsole vars leaked in):
  - an unrelated message was classified `new_task` (0.95, about 1.5 s including the `with-secrets` re-exec), blocked, `/clear`ed and re-sent; the fresh session answered it;
  - the transport chosen was tmux; the leaked Konsole target was rejected by the ancestor check;
  - in the fresh session, "why am I in a new session? that was wrong" got the SessionStart notice's undo steps with the right session id;
  - `/resume <old id>` plus re-sending the same text logged `returned_after_split` and was answered in place;
  - a follow-up ("make that email firmer") was classified `continue` (0.95, 0.9 s);
  - `new: …` split, and was re-sent without the prefix.
- **Not tested**: the Konsole transport outside tmux, multi-line messages, `same:` and `split off`.

## Bugs found in the end-to-end test (2026-10-24), and fixes

1. **The blocked prompt comes back into the input box.** This is undocumented; the hooks docs
   only say `suppressOriginalPrompt` hides it from the block message. Typing `/clear` therefore
   produced `…repaired./clear`, which was submitted as a normal message, classified again and
   split again, in a loop. Fix: the helper empties the input first (`\x15\x7f` per line), and a
   loop guard skips any split within 20 s of the last split from the same session.
2. **Leaked terminal env vars point at the wrong terminal.** tmux started from Konsole inherits
   `KONSOLE_DBUS_*`, and Konsole was checked first, so the helper targeted the outer Konsole
   session. That session was running a different, live Claude session; it was spared only
   because plain `qdbus` is the broken Qt5 chooser stub on this machine. Fix: tmux first, and an
   ancestor-PID check on every transport.
3. **`qdbus` vs `qdbus6`.** On Qt6-only KDE, `qdbus` fails ("could not find a Qt installation").
   The hook tries `qdbus6`, then `/usr/lib/qt6/bin/qdbus`, then `qdbus`.
4. **A `new:` prefix was re-sent as is,** so the fresh session would force-split again. It is now stripped.
5. **Undo matching looked at the hash only,** so the fresh session's moved copy counted as "brought
   back" and got the wrong context. It now also requires the original session id.
6. The dispatch helper's errors went to `/dev/null`. It now logs `dispatched` or `dispatch_error`.
   Also: when `.venv` is missing, the hook fails open silently. Claude Code records only a
   non-blocking error in the transcript, so a split that never happens may mean the venv is gone.

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

## Packaged plugin (2026-10-24)

The installable version of this hook, which uses the local int8 model and makes no API calls, is
[danielrosehill/New-Task-Split](https://github.com/danielrosehill/New-Task-Split).

- **Setup:** `/plugin install new-task-split@danielrosehill`, then `ntsctl install --shadow`.
- **On and off:** `ntsctl enable [--split|--shadow]` and `ntsctl disable`.
- **Update the model:** `ntsctl update-model`.
- **Remove:** `ntsctl uninstall`.

The plugin README has the full guide. This draft remains the research copy, including its Haiku teacher backend.
