# Prior art scan

Verified: **2026-10-16**, by a Claude Code agent using WebSearch, WebFetch and `gh repo view`.

The question from the voice note: has anyone already built "one conversation, many
context-isolated workers" — where something on every turn decides *continue / hand to the
worker that owns this / start a new worker*, and the new worker is a full parallel
orchestrator rather than a subagent?

How to read the confidence column:

- **Confirmed**: read on the primary source (vendor docs, the vendor's own announcement, or
  the GitHub repo via `gh`) on 2026-10-16.
- **Secondary**: only seen in third-party write-ups or search summaries. Treat as unverified.
- **Inferred**: my reading of what the source implies, not stated by it.

## Headline finding

**Anthropic has shipped almost exactly this idea as Claude Code Projects** (public beta, Pro and
Max plans). The project is one coordinating conversation. Claude routes each message you send:
it answers in place, starts a new thread, or passes the message to the thread already working
in that area. Each thread is a separate session with its own context window and branch. The
Overview pane shows every thread and its state. It works on claude.ai/code, the desktop app and
the iOS and Android apps, which is the surface the voice note was about.

So the core idea is no longer a gap inside Claude. What is still missing, below, is mostly about
the routing decision being explicit and inspectable, the tree view, nesting, and
harness-independence.

## Comparison table

"Routing" means: does something decide automatically, per message, whether that message starts
new isolated work?

| # | Work | What it is | Auto-routing per message | Worker = full session | Tree UI | Confidence |
|---|---|---|---|---|---|---|
| 1 | Claude Code Projects | One coordinating conversation that starts and routes to parallel cloud threads | **Yes**: model judgment by the coordinator | Yes | Grouped list by state, not a tree | Confirmed |
| 2 | Claude Code agent view (`claude agents`, `--bg`) | Supervisor that runs local background sessions in worktrees | No: the user dispatches | Yes | Grouped list | Confirmed |
| 3 | Claude Code agent teams | Lead plus teammates with a shared task list and mailbox | Partial: the lead spawns when it chooses to | Yes | Agent panel | Confirmed |
| 4 | Claude Code cross-session messaging | `ListAgents` and `SendMessage` between your sessions | No, but it is the plumbing for route-to-existing | n/a | `/list-agents` | Confirmed |
| 5 | Claude Code subagents, `/fork`, `/batch`, dynamic workflows | In-session delegation | Description-matched delegation only | No (subagent) | `/tasks` | Confirmed |
| 6 | opencode | Open-source coding agent. Subagents are child sessions you can navigate between | Description-matched subagent invocation | Child session | Parent/child navigation keys | Confirmed (docs); internals Secondary |
| 7 | Amp Handoff | Replace compaction with a fresh thread seeded from the old one | No: user-invoked `/handoff <goal>` | Yes (new thread) | No | Confirmed |
| 8 | topic-switch (Claude Code plugin) | Hooks that detect file-area drift and nudge to compact | Detects; suggests compaction, not a new session | No | No | Confirmed (listing); repo exists |
| 9 | Pantheon `auto-compact-topic-shift` skill | Scored topic-shift detector with thresholds | Yes: auto at ≥0.75, suggest at ≥0.40; `new_session` action available | Signals only | No | Confirmed (listing); repo exists |
| 10 | Devin managed Devins | Coordinator Devin splits a task across child Devins in their own VMs | Splits one big task. Per-message routing not described | Yes | Session links | Confirmed |
| 11 | Claude Squad | TUI over tmux and worktrees for many agent CLIs | No | Yes | List | Confirmed (repo) |
| 12 | Crystal (now Nimbalyst) | Electron app, parallel sessions in worktrees | No | Yes | List | Confirmed (repo) |
| 13 | Vibe Kanban | Kanban board dispatching agents into worktrees | No: board-driven | Yes | Kanban | Confirmed (repo) |
| 14 | Conductor | Mac app for parallel Claude Code workspaces | No | Yes | List | Secondary |
| 15 | Cursor cloud agents (formerly background agents) | Cloud VMs, branch per agent, PR out | No | Yes | List | Secondary |
| 16 | OpenAI Codex cloud tasks | Sandbox per task, diff or PR out | No | Yes | List | Secondary |
| 17 | OpenHands | Open-source agent platform | Not found | n/a | n/a | Repo confirmed; feature not found |

## Details

### 1. Claude Code Projects — closest match

Source: <https://code.claude.com/docs/en/claude-projects>

Confirmed from the docs:

- "A project is one ongoing conversation where Claude coordinates a stream of related work for
  you. You tell it what needs doing and it starts a thread for each task."
- Routing: "Claude starts a thread for each piece of work or passes it to the thread already
  working in that area, and answers quick questions in place." Also: "Several unrelated tasks in
  one message become separate threads." This is the same three-way decision as
  `continue | route_to_existing | spawn_new` in [`spec.md`](spec.md).
- Threads: "Each is a separate session with its own context window... A cloud thread works on
  its own branch and opens a pull request when the work calls for one."
- Context: "You don't manage context windows in a project. Threads compact automatically, and
  the conversation works from recent messages, recent threads, and project memory rather than
  its full history."
- Controls are natural-language preferences ("Propose threads and wait for my go-ahead", "Run
  at most two threads at a time", "Answer that here instead of starting a thread"). The docs
  say they are "instructions Claude keeps to, not enforced settings".
- Overview groups threads by state: Ready for review, Waiting on you, Working, Landing, Idle,
  Resolved.
- Availability: public beta on Pro and Max, rolling out gradually; "not available on Team or
  Enterprise plans yet". Works on claude.ai/code, the desktop app and the mobile apps. A thread
  can run on your own machine through Remote Control.

Gaps compared with the voice note (inferred from the docs):

- The routing decision is the coordinator model's judgment. It is not a separate classifier
  with a typed output, a confidence score or a log you can audit and tune.
- The Overview is a grouped list. It is not the session → thread → subagent tree Daniel
  described.
- The docs do not describe nesting, such as a thread starting its own threads.
- It is Anthropic-hosted and Claude-only. It is not an open harness.
- Not yet on Team or Enterprise plans.

Not verified: whether Daniel's account has the rollout. Check for **Projects** in the
claude.ai/code sidebar.

### 2–5. The other Claude Code primitives

Source: <https://code.claude.com/docs/en/agents>, which compares five ways to run parallel work:
subagents, agent view, agent teams, dynamic workflows and projects.

- **Agent view** (<https://code.claude.com/docs/en/agent-view>, research preview): "Each
  background session is a full Claude Code conversation that keeps running without a terminal
  attached." Before editing files, a session moves into its own worktree under
  `.claude/worktrees/`. The user dispatches every session ("you dispatch each one"). `/fork`
  copies the current conversation into a new background session. This is the **local spawn
  mechanism** a harness could drive.
- **Agent teams** (<https://code.claude.com/docs/en/agent-teams>): experimental, enabled with
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. Teammates are separate instances with their own
  context, a shared task list and a mailbox. Limits: "No nested teams: teammates cannot spawn
  their own teammates." Teammates are not put in worktrees. This is the closest primitive for
  "parallel orchestrators", but the team is scoped to one task. It is not a router for an
  incoming stream of unrelated tasks.
- **Cross-session messaging** (<https://code.claude.com/docs/en/cross-session-messaging>):
  `ListAgents` and `SendMessage` reach other local, background and cloud sessions. Plain text
  only. Each session exports `CLAUDE_CODE_MESSAGING_SOCKET` to hooks, so **a hook can post into
  a session**. This is the plumbing for `route_to_existing`.
- **Hooks** (<https://code.claude.com/docs/en/hooks>): `UserPromptSubmit` receives `prompt`
  and `transcript_path`. It can block with `decision: "block"` and `reason`, inject
  `additionalContext`, and set `sessionTitle`. It supports all five hook types, including
  `type: "prompt"` (a single LLM evaluation) and `type: "agent"`. It cannot rewrite the prompt.
  The default timeout on this event is 30 seconds. So a classifier hook is directly buildable.

### 6. opencode

Sources: <https://opencode.ai/docs/agents/>, repo <https://github.com/anomalyco/opencode>
(`sst/opencode` redirects there; about 214k stars).

Confirmed: there are primary agents (Build, Plan) and subagents (General, Explore, Scout).
Subagents create **child sessions**, and the TUI has keys to move between them: Leader+Down
enters a child, Left and Right cycle siblings, Up returns to the parent. This is probably what
Daniel remembered. It is the nearest thing to the tree navigation he described, but the children
are subagents spawned by description matching. They are not routed parallel orchestrators.

Secondary: a source-code study, arXiv 2609.00006 ("Harness Engineering: Anatomy, Architecture,
and Evolution of Coding Agents"), says the task tool creates a session with a parent ID and that
results return to the parent as final text. I did not read the paper itself.

### 7. Amp Handoff

Source: <https://ampcode.com/news/handoff> (2025-10-23).

Confirmed: Handoff replaced compaction. "Instead of summarizing a thread, you're extracting from
it what matters for your next task." You give a goal, Amp drafts a seed prompt and a list of
files for a new thread, and you review the draft. The user invokes it. It is the right
philosophy, a fresh thread instead of compaction, without the automatic trigger.

Secondary: a later report says Amp's rebuilt CLI ("Neo", May 2026) went back to automatic
compaction. Not checked.

### 8–9. Topic-shift detectors (the classifier half)

- **topic-switch**: <https://github.com/hi-lei/topic-switch> (exists; 0 stars, last push
  2026-04-03). Listing: <https://claudepluginhub.com/plugins/nusmql-topic-switch>. A
  `PostToolUse` hook records which "topic roots" (directory globs) you touch, and
  `UserPromptSubmit` nudges "save context and compact?" when the root changes. Detection is
  pure bash with no LLM call. It compacts. It does not spawn.
- **Pantheon `auto-compact-topic-shift`**:
  <https://github.com/Duskript/Pantheon/tree/main/god-packages/shared-skills/auto-compact-topic-shift>
  (repo exists; 16 stars). It scores each message as lexical change (0–0.4) plus semantic
  distance (0–0.4) plus structural cues such as "anyway" (0–0.2). It auto-acts at ≥0.75 and
  suggests at ≥0.40. The action is `compress` (default) or `new_session`. The scoring is done by
  the agent following the skill, not by a separate model. Inferred: it targets the Hermes agent.

These are the only things found that put a **scored, thresholded continue-vs-new decision** on
every turn. Neither routes to an existing worker or spawns a parallel orchestrator.

### 10. Devin managed Devins

Source: <https://cognition.com/blog/devin-can-now-manage-devins> (2026-03-19).

Confirmed: a coordinator session splits a large task across managed Devins, each in its own VM.
It monitors them, messages them mid-task and compiles results. Each child has its own session
link. The decision is top-down decomposition of one task. The post does not describe routing a
stream of unrelated user messages.

### 11–16. Parallel-session managers

All of these give you isolated parallel sessions, usually one git worktree per session. **The
human does the routing** in every one of them.

- Claude Squad: <https://github.com/smtg-ai/claude-squad>. "Manage multiple AI terminal agents
  like Claude Code, Codex, OpenCode, and Amp." 8.6k stars, last push 2026-08-20. Built on tmux
  and worktrees.
- Crystal: <https://github.com/stravu/crystal>. The repo description says "Crystal is now
  Nimbalyst". Last push 2026-02-26.
- Vibe Kanban: <https://github.com/BloopAI/vibe-kanban>. 28.4k stars, last push 2026-09-19.
  Secondary: the original company shut down in April 2026 and the repo is community-maintained.
- Conductor: <https://www.conductor.build/>. Secondary.
- Cursor cloud agents and Codex cloud: secondary write-ups only, for example
  <https://www.morphllm.com/cursor-background-agents>. Each agent or task gets a VM or sandbox
  and produces a PR.

### 17. OpenHands

<https://github.com/OpenHands/OpenHands> (`All-Hands-AI/OpenHands` redirects there). I found
nothing about automatic per-message routing to parallel conversations. That is a gap in the
search, not a confirmed absence.

## The research case (why fresh threads beat one long thread)

- **Chroma, "Context Rot"** (Hong, Troynikov and Huber, 2025-07-14):
  <https://www.trychroma.com/research/context-rot>. Confirmed: 18 models all degraded as input
  length grew, even on trivial tasks, and distractors compounded the drop. The finding that
  matters most here is from LongMemEval: focused prompts of about 300 tokens beat full
  conversation histories of about 113k tokens across every model family, including with
  thinking enabled. That is direct evidence for "don't carry unrelated history".
- **Anthropic, "Effective context engineering for AI agents"** (2025-09-29):
  <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>.
  Confirmed: context is "a finite resource with diminishing marginal returns". The post covers
  compaction ("the art of compaction lies in the selection of what to keep versus what to
  discard"), structured note-taking, and sub-agents with clean context windows that return
  summaries of 1,000–2,000 tokens.
- **Conversation Tree Architecture** (arXiv 2603.21278, March 2026):
  <https://www.alphaxiv.org/abs/2603.21278>. Proposes conversations as trees of
  context-isolated nodes, with rules for context flowing between parent and child. The abstract
  does not describe automatic routing of new messages, and the authors say evaluation is in
  progress.
- **LLM topic segmentation of chat threads**: arXiv 2605.19627 used GPT-4.1 with rules to split
  multi-topic operator chats into segments. Secondary; I did not read it.
- Older work on automatic new-topic identification in search logs (Özmutlu et al.) reports high
  shift-detection accuracy from time-gap and reformulation features. Possibly useful as cheap
  classifier features. Secondary.

## Verdict

**Build on Claude Code Projects. Do not rebuild it.** The core of the voice note (one
conversation, a coordinator that routes each message to continue, an existing worker or a new
parallel session, workers as full sessions on their own branches, mobile-first) shipped as
Claude Code Projects. For Daniel's own use, the first step is to check that Projects is enabled
on his account and use it.

**Gaps that remain**, and what this repo could still do:

1. **An explicit, inspectable router.** Projects routes by coordinator judgment, with soft
   natural-language controls. Nothing found publishes a typed routing decision with a
   confidence score and a decision log that can be evaluated against labelled transcripts. The
   topic-shift detectors (topic-switch, Pantheon) score the decision but only compact or signal.
   **A small routing classifier plus an eval set is the clearest open contribution.**
2. **The tree view.** No product found shows session → parallel threads → subagents as one
   tree. Projects and agent view use state-grouped lists, and opencode has parent/child
   navigation without a whole-tree view.
3. **Nesting.** Agent teams forbid nested teams, and the Projects docs do not describe threads
   starting threads.
4. **Harness-independence.** Every router found is tied to one vendor. An open harness that
   does the routing over Claude Code, opencode or Codex CLI sessions, using agent view,
   `claude --bg` and cross-session messaging as the spawn and route plumbing, does not appear
   to exist.
5. **Local and Team/Enterprise users.** Projects is cloud-first and Pro/Max only for now. A
   `UserPromptSubmit` hook plus `claude --bg` gives an approximation on the local CLI.
