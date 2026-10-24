#!/usr/bin/env python3
"""Build blind verification requests: a second model labels each candidate without seeing the
generator's intended label. Only agreeing rows become clean labels.

    python3 verify_requests.py ../raw/out-gen.jsonl > ../raw/requests-verify.jsonl
"""
import json, sys

SYSTEM = """You label data for a classifier used inside AI agents. You see a recent agent \
conversation and several candidate next user messages, each considered on its own as the very \
next turn. For each, decide:

- "continue": the message needs or builds on the conversation so far (follow-up, correction, \
approval, question about what was done, extension, or any explicit or implicit reference back).
- "new_task": a fresh agent with no memory of this conversation could handle it just as well. \
Being in the same workspace does not make it the same task.
- "ambiguous": reasonable people would disagree.

Give a confidence from 0 to 1 for each."""

SCHEMA = {"type": "object", "properties": {"labels": {"type": "array", "items": {
    "type": "object", "properties": {
        "index": {"type": "integer"},
        "label": {"type": "string", "enum": ["continue", "new_task", "ambiguous"]},
        "confidence": {"type": "number"}},
    "required": ["index", "label", "confidence"], "additionalProperties": False}}},
    "required": ["labels"], "additionalProperties": False}

for line in open(sys.argv[1]):
    row = json.loads(line)
    r = row.get("result")
    if not isinstance(r, dict):
        continue
    convo = "\n".join(f"USER: {t['user']}\nAGENT: {t['agent']}" for t in r["turns"])
    cands = "\n".join(f"[{i}] {c['message']}" for i, c in enumerate(r["candidates"]))
    print(json.dumps({"id": row["id"], "system": SYSTEM, "schema": SCHEMA,
                      "user": f"Workspace: {r['workspace']}\n\nConversation:\n{convo}\n\nCandidates:\n{cands}"}))
