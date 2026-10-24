#!/usr/bin/env python3
"""Build the batch request JSONL for synthetic agent-session scenarios (Agent-Task-Break-Detector).

Each request asks the generator for one short agent session plus six candidate next user
messages, each labelled `continue` or `new_task` by construction. Seeds (agent kind, domain, task,
user style, session length) are sampled from the lists below so scenarios don't collapse onto a
few templates.

    python3 make_requests.py --n 20 --seed 1 > ../raw/requests-pilot.jsonl
"""
import argparse, json, random

# (agent kind, domains). About half the scenarios are coding agents, the rest other agent work.
AGENTS = {
    "coding agent in a repository": [
        "TypeScript + Next.js podcast website", "Astro static blog", "Python FastAPI service",
        "Python data pipeline (pandas, DuckDB)", "Django admin app", "Rust CLI tool", "Go microservice",
        "Kotlin Android app", "Swift iOS app", "Flutter app", "Electron desktop app",
        "Docker Compose homelab stack", "Terraform on AWS", "Kubernetes Helm charts",
        "GitHub Actions CI", "PyTorch training scripts", "Postgres schema and migrations",
        "C++ CMake library", "Ruby on Rails shop", "Home Assistant YAML config",
        "Chrome extension", "MCP server in Python", "agent plugin with skills and hooks",
        "Ansible playbooks", "Unity C# game prototype", "dotfiles repo",
    ],
    "research assistant agent with web search": [
        "comparing laptops to buy", "literature review on speech recognition", "market research for a SaaS idea",
        "planning a family trip", "checking a medication's interactions", "finding grant opportunities",
        "background on a historical event", "evaluating cloud backup providers",
    ],
    "sysadmin / ops agent on a Linux machine": [
        "home server running Docker", "laptop after an OS upgrade", "VPS hosting a website",
        "NAS and backup jobs", "home network with a router and VLANs", "printer and audio setup",
    ],
    "writing and documents agent": [
        "drafting a book chapter", "editing a grant proposal", "writing a blog post series",
        "preparing a slide deck", "formatting a CV", "writing project documentation",
    ],
    "data analysis agent": [
        "sales spreadsheet analysis", "household budget CSVs", "survey results", "server log analysis",
        "sports statistics", "energy usage readings",
    ],
    "personal assistant agent with email and calendar": [
        "inbox triage", "scheduling meetings", "drafting replies to suppliers", "organising a move",
        "tracking subscriptions", "planning an event",
    ],
    "browser automation agent": [
        "filling in a government form", "comparing prices across shops", "downloading invoices from portals",
        "updating a website CMS", "monitoring a listing site",
    ],
}
TASKS = {
    "coding agent in a repository": [
        "fixing a bug", "adding a feature", "refactoring a module", "writing tests", "debugging a failing CI run",
        "updating dependencies", "investigating slow performance", "writing documentation",
        "setting up deployment", "migrating a database schema", "fixing a build error", "adding logging",
    ],
}
STYLES = [
    "terse, lowercase, no punctuation",
    "polite and complete sentences",
    "dictated by voice: long run-on sentences, filler words, self-corrections ('wait, no, I mean')",
    "impatient, short imperative commands",
    "chatty, thinks out loud before asking",
    "non-native English speaker, small grammar slips",
    "precise engineer, names files and functions exactly",
    "vague, refers to things loosely ('that thing', 'the page')",
]

SYSTEM = """You write synthetic training data for a classifier used inside AI agents of any kind \
(coding agents such as Claude Code or Codex CLI, research, ops, writing, data and assistant agents). The classifier reads the recent conversation and \
a new user message and decides:

- "continue": the new message needs the conversation so far. Follow-ups, corrections, approvals, \
questions about what was just done, extensions of the current work, or anything that refers back \
("that", "it", "the fix", "as before", "also do X to those files").
- "new_task": the message starts work a fresh agent with no memory of the conversation could do \
just as well. Same repository or workspace does NOT make it the same task.

Write a realistic session for the given agent and domain: a one-line description of the \
workspace, then the requested number of exchanges. User turns are written in the \
requested style. Agent turns are short summaries of what the agent did (1 to 4 sentences, with concrete \
names: files, commands, pages, people, figures), like the tail of a real agent reply. No raw tool output.

Then write exactly 6 candidate NEXT user messages, each a plausible next turn on its own, in the \
same user style:
1. continue / follow_up: an obvious follow-up to the last exchange
2. continue / hard_negative: sounds like a new topic, or starts with "separate question", "unrelated \
but", "while you're here", yet actually depends on the conversation
3. continue / implicit_reference: refers back only implicitly (pronouns, "the other one", "same for \
the tests")
4. new_task / same_workspace: a different task in the same workspace or domain, no dependency on the conversation
5. new_task / subtle_pivot: no explicit "new topic" marker, shares some vocabulary with the session, \
but is genuinely independent work
6. new_task / far: clearly unrelated (different area, or a general question)

Variety rules, because a classifier must not learn shortcuts from surface phrases:
- Vary message length (from 3 words to 80).
- Only some hard_negative messages may open with a topic-change phrase, and vary it ("different \
thing", "quick one", "btw", "oh also", "random but", or none at all). Never use "separate question".
- Most new_task messages have no signal phrase at all. Some may even start with "ok", "also" or "and".
- "far" is usually a request to do some unrelated work, only sometimes a general knowledge question. \
Avoid "what's the difference between".
- Keep each rationale under 15 words."""

SCHEMA = {
    "type": "object",
    "properties": {
        "workspace": {"type": "string"},
        "turns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"user": {"type": "string"}, "agent": {"type": "string"}},
                "required": ["user", "agent"],
                "additionalProperties": False,
            },
        },
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "label": {"type": "string", "enum": ["continue", "new_task"]},
                    "kind": {"type": "string", "enum": [
                        "follow_up", "hard_negative", "implicit_reference", "same_workspace", "subtle_pivot", "far"]},
                    "rationale": {"type": "string"},
                },
                "required": ["message", "label", "kind", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["workspace", "turns", "candidates"],
    "additionalProperties": False,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--prefix", default="s")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    for i in range(a.n):
        agent = "coding agent in a repository" if rng.random() < 0.5 else rng.choice(list(AGENTS)[1:])
        seed = {
            "agent": agent, "domain": rng.choice(AGENTS[agent]),
            "task": rng.choice(TASKS[agent]) if agent in TASKS else None,
            "style": rng.choice(STYLES), "exchanges": rng.randint(2, 5),
        }
        user = (f"Agent: {seed['agent']}\nDomain: {seed['domain']}\n"
                + (f"Current task: {seed['task']}\n" if seed["task"] else "")
                + f"User style: {seed['style']}\nNumber of exchanges: {seed['exchanges']}")
        print(json.dumps({"id": f"{a.prefix}{a.seed}-{i:05d}", "system": SYSTEM, "user": user,
                          "schema": SCHEMA, "seed": seed}))


if __name__ == "__main__":
    main()
