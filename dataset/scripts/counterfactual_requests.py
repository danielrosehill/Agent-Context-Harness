#!/usr/bin/env python3
"""v0.2 matched pairs: for each agreed new_task message, ask the generator for a session in which
that exact message is a natural CONTINUATION. The same text then appears under both labels, so a
model can't score from the message alone (v0.1's message-only TF-IDF baseline reached 97%).

    python3 counterfactual_requests.py ../hf/data > ../raw/requests-cf.jsonl
"""
import json, sys
from pathlib import Path

SYSTEM = """You write synthetic training data for a classifier inside AI agents. It decides whether \
a new user message continues the current conversation or starts an unrelated task.

You get a user message. Write a realistic agent session (workspace line + the requested number of \
exchanges) to which this exact message is a natural next turn that CONTINUES the work: a fresh agent \
without this conversation would be missing something it needs (which item, which file, which \
decision, what was already tried, the plan the message is a step of).

Rules:
- Do not change the message, and don't quote it in the session.
- Make the link real but not always lexical. Vary it: sometimes the message is the obvious next \
step of a plan the agent laid out; sometimes it continues an earlier exchange, not the last; \
sometimes it shares few words with the session and depends on it through what was decided.
- User turns use the given style. Agent turns are 1 to 4 sentence summaries of what the agent did, \
with concrete names, like the tail of a real reply. No raw tool output.
- Keep "why" under 15 words: what the message depends on."""

SCHEMA = {"type": "object", "properties": {
    "workspace": {"type": "string"},
    "turns": {"type": "array", "items": {"type": "object", "properties": {
        "user": {"type": "string"}, "agent": {"type": "string"}},
        "required": ["user", "agent"], "additionalProperties": False}},
    "why": {"type": "string"}},
    "required": ["workspace", "turns", "why"], "additionalProperties": False}

for f in sorted(Path(sys.argv[1]).glob("*.jsonl")):
    for line in open(f):
        r = json.loads(line)
        if not (r["agreed"] and r["label"] == "new_task"):
            continue
        n = max(2, min(5, len(r["context"])))
        user = (f"Agent: {r['agent_kind']}\nDomain: {r['domain']}\nUser style: {r['user_style']}\n"
                f"Number of exchanges: {n}\n\nMessage:\n{r['message']}")
        print(json.dumps({"id": f"cf-{r['id']}", "system": SYSTEM, "user": user, "schema": SCHEMA,
                          "source": r["id"]}))
