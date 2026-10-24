#!/usr/bin/env python3
"""new-task-split: move a prompt that starts an unrelated task into a fresh Claude Code session.

One script, three entry points:

  UserPromptSubmit hook   classify the prompt; on "new task" block it here and re-send it
                          after /clear into the same terminal
  SessionStart hook       (source=clear) tell the fresh session it was auto-split, and how to undo
  --dispatch              detached helper that types "/clear" and the prompt into the terminal

Claude Code hooks cannot run /clear or swap sessions (hooks docs, checked 2026-10-24), so the
terminal itself is driven: Konsole over D-Bus, or tmux send-keys. Anything else falls back to
copying the prompt to the clipboard and asking the user to /clear and paste.

Fails open: any error, timeout or missing key means the prompt goes through untouched.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("NEW_TASK_SPLIT_STATE", Path.home() / ".cache" / "new-task-split"))
MODEL = os.environ.get("NEW_TASK_SPLIT_MODEL", "claude-haiku-5-5")
THRESHOLD = float(os.environ.get("NEW_TASK_SPLIT_THRESHOLD", "0.85"))
MIN_PRIOR_PROMPTS = 2      # a session this young has no context worth protecting
MIN_PROMPT_CHARS = 40      # "yes", "push it", "looks good" are always continuations
RETURN_WINDOW = 30 * 60    # a split prompt re-sent within this many seconds is an undo
KEEP_PREFIXES = ("same:", "here:")
FORCE_PREFIXES = ("new:", "split:")

SYSTEM = """You decide whether a coding-agent user's new message needs the conversation so far.

Answer "new_task" only when the message starts work that is unrelated to the recent conversation \
and could be done well by a fresh agent that has never seen it: a different bug, feature, file \
area or question, with no reference back ("that", "it", "the same", "also fix", "as above") to \
what came before. Same repository is not the same task.

Answer "continue" when the message follows up, corrects, approves, asks about or extends the \
recent work, or when you are unsure. A wrong "new_task" throws away the agent's working context; \
a wrong "continue" only costs some extra context. Be conservative.
Keep "reason" under 12 words."""

SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["continue", "new_task"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["decision", "confidence", "reason"],
    "additionalProperties": False,
}


# ---------- state ----------

def _state_file(session_id: str) -> Path:
    return STATE / "sessions" / f"{session_id}.json"


def load_state(session_id: str) -> dict:
    try:
        return json.loads(_state_file(session_id).read_text())
    except (OSError, ValueError):
        return {}


def save_state(session_id: str, state: dict) -> None:
    path = _state_file(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def log(record: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(STATE / "decisions.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(" ".join(prompt.split()).encode()).hexdigest()[:16]


def split_just_now(session_id: str, window: float = 20.0) -> bool:
    """Loop guard: this session handed a message off moments ago, so don't split again."""
    try:
        last = json.loads((STATE / "splits.jsonl").read_text().splitlines()[-1])
    except (OSError, ValueError, IndexError):
        return False
    return last.get("from") == session_id and time.time() - last["t"] < window


def recently_split(h: str, session_id: str) -> bool:
    """True if this exact prompt was auto-split out of this session recently: the user brought it
    back (undo), so it belongs here. The fresh session receiving the moved copy doesn't match."""
    try:
        lines = (STATE / "splits.jsonl").read_text().splitlines()
    except OSError:
        return False
    now = time.time()
    for line in reversed(lines[-200:]):
        rec = json.loads(line)
        if rec["hash"] == h and rec.get("from") == session_id and now - rec["t"] < RETURN_WINDOW:
            return True
    return False


# ---------- transcript ----------

def read_turns(transcript_path: str) -> tuple[list[str], str]:
    """Return (user prompts typed so far, last assistant text). Tool results and meta lines skipped."""
    prompts: list[str] = []
    last_assistant = ""
    try:
        lines = Path(transcript_path).read_text().splitlines()
    except OSError:
        return prompts, last_assistant
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("isMeta") or entry.get("isSidechain"):
            continue
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "user":
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
            else:
                continue
            if text.strip() and not text.lstrip().startswith("<"):
                prompts.append(text)
        elif entry.get("type") == "assistant" and isinstance(content, list):
            text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
            if text.strip():
                last_assistant = text
    return prompts, last_assistant


# ---------- classifier ----------

def classify(prompt: str, prior_prompts: list[str], last_assistant: str, title: str | None) -> dict:
    # Raw HTTP rather than the anthropic SDK: importing the SDK costs ~2 s on this laptop
    # (measured 2026-10-24, anthropic 2.3.0), and this hook blocks every prompt while it runs.
    import urllib.request

    recent = "\n\n".join(f"[user {i + 1}] {p[:600]}" for i, p in enumerate(prior_prompts[-4:]))
    body = (
        (f"Session title: {title}\n\n" if title else "")
        + f"Recent user messages:\n{recent}\n\n"
        + f"Agent's last reply (tail):\n{last_assistant[-1500:]}\n\n"
        + f"New user message:\n{prompt[:2000]}"
    )
    payload = {
        "model": MODEL,
        "max_tokens": 256,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": body}],
        "thinking": {"type": "disabled"},  # Haiku 5.5 allows this at effort <= high
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        resp = json.load(r)
    out = json.loads(next(b["text"] for b in resp["content"] if b["type"] == "text"))
    out["usage"] = {"in": resp["usage"]["input_tokens"], "out": resp["usage"]["output_tokens"]}
    return out


# ---------- terminal transport ----------

def _ancestors() -> set[int]:
    """PIDs of this process and its ancestors (Linux /proc). Empty if unavailable."""
    pids, pid = set(), os.getpid()
    try:
        while pid > 1:
            pids.add(pid)
            pid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return set()
    return pids


def _qdbus() -> str | None:
    # Plain `qdbus` is often the Qt5 chooser stub and fails on Qt6-only KDE installs.
    return next((q for q in ("qdbus6", "/usr/lib/qt6/bin/qdbus", "qdbus") if shutil.which(q)), None)


def _target_pid(kind: str) -> int | None:
    try:
        if kind == "tmux":
            out = subprocess.run(["tmux", "display-message", "-p", "-t", os.environ["TMUX_PANE"], "#{pane_pid}"],
                                 capture_output=True, text=True, timeout=3, check=True).stdout
        else:
            out = subprocess.run([_qdbus(), os.environ["KONSOLE_DBUS_SERVICE"], os.environ["KONSOLE_DBUS_SESSION"],
                                  "org.kde.konsole.Session.foregroundProcessId"],
                                 capture_output=True, text=True, timeout=3, check=True).stdout
        return int(out.strip())
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


def transport() -> str:
    """Pick the terminal to type into, innermost first, and only if it provably runs this session.

    Env vars leak into nested terminals (tmux started from Konsole inherits KONSOLE_DBUS_*), so a
    candidate is used only when its process is one of our ancestors. Otherwise: clipboard."""
    candidates = []
    if os.environ.get("TMUX_PANE") and shutil.which("tmux"):
        candidates.append("tmux")
    if os.environ.get("KONSOLE_DBUS_SERVICE") and os.environ.get("KONSOLE_DBUS_SESSION") and _qdbus():
        candidates.append("konsole")
    ours = _ancestors()
    for kind in candidates:
        if _target_pid(kind) in ours:
            return kind
    return "clipboard"


def send_text(kind: str, text: str) -> None:
    if kind == "konsole":
        subprocess.run([_qdbus(), os.environ["KONSOLE_DBUS_SERVICE"], os.environ["KONSOLE_DBUS_SESSION"],
                        "org.kde.konsole.Session.sendText", text], check=True, capture_output=True)
    elif kind == "tmux":
        subprocess.run(["tmux", "send-keys", "-t", os.environ["TMUX_PANE"], "-l", text], check=True)


def dispatch(kind: str, prompt_file: str) -> None:
    """Runs detached after the hook has returned: wait for the block to land, /clear, re-send."""
    prompt = Path(prompt_file).read_text()
    Path(prompt_file).unlink(missing_ok=True)
    time.sleep(float(os.environ.get("NEW_TASK_SPLIT_DELAY", "1.0")))
    # Claude Code (2.1.310, undocumented) puts a blocked prompt back in the input box, so typing
    # /clear straight away appends to it ("…text/clear") and submits a normal message. Empty the
    # box first: Ctrl+U clears the current line, Backspace joins the line above.
    send_text(kind, "\x15\x7f" * (prompt.count("\n") + 1))
    time.sleep(0.3)
    send_text(kind, "/clear")
    time.sleep(0.3)
    send_text(kind, "\r")
    time.sleep(float(os.environ.get("NEW_TASK_SPLIT_CLEAR_WAIT", "2.0")))
    # Multi-line text goes in as a bracketed paste so its newlines don't submit early.
    send_text(kind, f"\x1b[200~{prompt}\x1b[201~" if "\n" in prompt else prompt)
    time.sleep(0.3)
    send_text(kind, "\r")


def hand_off(prompt: str, session_id: str) -> str:
    """Start the move; return the transport used."""
    kind = transport()
    log({"session": session_id, "decision": "hand_off", "transport": kind})
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / "splits.jsonl", "a") as f:
        f.write(json.dumps({"t": time.time(), "hash": prompt_hash(prompt), "from": session_id}) + "\n")
    # Marker read by the SessionStart hook in the fresh session.
    (STATE / "pending-origin.json").write_text(json.dumps({"t": time.time(), "from": session_id}))
    if kind == "clipboard":
        if shutil.which("wl-copy"):
            subprocess.run(["wl-copy"], input=prompt.encode(), check=False)
        return kind
    pf = STATE / f"pending-{session_id}.txt"
    pf.write_text(prompt)
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--dispatch", kind, str(pf)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return kind


# ---------- hook outputs ----------

def emit(obj: dict) -> None:
    print(json.dumps(obj))
    sys.exit(0)


def block(reason: str) -> None:
    emit({"decision": "block", "reason": reason,
          "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "suppressOriginalPrompt": True}})


def add_context(text: str) -> None:
    emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}})


# ---------- events ----------

def on_prompt(event: dict) -> None:
    prompt = event.get("prompt", "")
    sid = event.get("session_id", "unknown")
    stripped = prompt.strip()
    low = stripped.lower()
    state = load_state(sid)

    if low in ("split off", "split on"):
        state["disabled"] = low == "split off"
        save_state(sid, state)
        block(f"new-task-split {'off' if state['disabled'] else 'on'} for this session.")
    if os.environ.get("NEW_TASK_SPLIT") == "off" or state.get("disabled"):
        sys.exit(0)
    if low.startswith(KEEP_PREFIXES):
        log({"session": sid, "decision": "kept_by_prefix"})
        sys.exit(0)
    # Slash commands, shell escapes, and machine-sent turns (task notifications, peer messages).
    if stripped[:1] in ("/", "!", "<") or not stripped:
        sys.exit(0)
    forced = low.startswith(FORCE_PREFIXES)
    if forced:
        # Re-send without the prefix, or the fresh session would split it again.
        prompt = stripped.split(":", 1)[1].lstrip()
    h = prompt_hash(prompt)
    if recently_split(h, sid):
        log({"session": sid, "decision": "returned_after_split", "hash": h})
        add_context("new-task-split had moved this exact message to a fresh session; the user "
                    "brought it back here, so it belongs to this conversation. Answer it here.")

    if not forced:
        if len(stripped) < MIN_PROMPT_CHARS:
            sys.exit(0)
        prior, last_assistant = read_turns(event.get("transcript_path", ""))
        if len(prior) < MIN_PRIOR_PROMPTS:
            sys.exit(0)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            # Nothing is exported on this machine; fetch the key only for turns that get this far.
            if shutil.which("with-secrets") and not os.environ.get("NEW_TASK_SPLIT_REEXEC"):
                ev = STATE / f"event-{sid}.json"
                ev.parent.mkdir(parents=True, exist_ok=True)
                ev.write_text(json.dumps(event))
                os.environ["NEW_TASK_SPLIT_REEXEC"] = "1"
                os.execvp("with-secrets", ["with-secrets", sys.executable, str(Path(__file__).resolve()),
                                           "--event", str(ev)])
            log({"session": sid, "decision": "skipped_no_key"})
            sys.exit(0)
        t0 = time.time()
        try:
            verdict = classify(prompt, prior, last_assistant, event.get("session_title"))
        except Exception as e:  # fail open
            log({"session": sid, "decision": "error", "error": f"{type(e).__name__}: {e}"[:300]})
            sys.exit(0)
        verdict["ms"] = int((time.time() - t0) * 1000)
        log({"session": sid, "hash": h, "preview": stripped[:120], **verdict})
        if verdict["decision"] != "new_task" or verdict["confidence"] < THRESHOLD:
            sys.exit(0)
        why = verdict["reason"]
    else:
        why = "forced with a new:/split: prefix"

    if split_just_now(sid):
        log({"session": sid, "decision": "skipped_loop_guard"})
        sys.exit(0)
    kind = hand_off(prompt, sid)
    undo = "Undo: /resume and pick the previous session, then re-send; it won't be split again."
    if kind == "clipboard":
        block(f"New task detected ({why}). Run /clear, then paste: the message is on your clipboard. {undo}")
    block(f"↪ New task detected ({why}). Moving it to a fresh session… {undo} "
          f"Start a message with 'same:' to keep it here, or type 'split off'.")


def on_session_start(event: dict) -> None:
    if event.get("source") != "clear":
        sys.exit(0)
    marker = STATE / "pending-origin.json"
    try:
        origin = json.loads(marker.read_text())
    except (OSError, ValueError):
        sys.exit(0)
    if time.time() - origin["t"] > 60:
        sys.exit(0)
    marker.unlink(missing_ok=True)
    emit({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": (
            "This session was started automatically by the new-task-split hook: the user's next "
            "message looked unrelated to their previous session "
            f"({origin['from']}), so it was moved here. If the user says the split was wrong, "
            "tell them to run /resume, choose that session, and re-send the message; the hook "
            "recognises a returned message and will not split it again."),
    }})


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--dispatch":
        try:
            dispatch(sys.argv[2], sys.argv[3])
            log({"decision": "dispatched", "transport": sys.argv[2]})
        except Exception as e:  # stdout/stderr are /dev/null here, so this log is the only trace
            log({"decision": "dispatch_error", "transport": sys.argv[2], "error": f"{type(e).__name__}: {e}"[:300]})
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--event":
        event = json.loads(Path(sys.argv[2]).read_text())
        Path(sys.argv[2]).unlink(missing_ok=True)
    else:
        event = json.load(sys.stdin)
    name = event.get("hook_event_name")
    if name == "UserPromptSubmit":
        on_prompt(event)
    elif name == "SessionStart":
        on_session_start(event)


if __name__ == "__main__":
    main()
