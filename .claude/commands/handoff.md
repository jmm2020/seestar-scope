---
description: Save session state to the Memory Domain (NOT a file) for next-session continuity
---

# Handoff — Save to Memory Domain

## Objective

Capture session state so the next session can continue without context loss. **The Memory Domain is the canonical store** — do NOT write `HANDOFF.md` or any other file. Memories get embeddings, auto-linking, Kafka publishing, foresight, perspective, graph context. A markdown file on disk is dead — not searchable, not embedded, not connected to other memories.

## When to Use

- Before ending a long session where work will continue later
- Before hitting context limits (proactive, not reactive)
- When switching phases (research → implementation, or implementation → debug)
- When handing off between human and AI, or between AI sessions

## Process

### 1. Analyze the current session

Review what happened:

- Original goal or task?
- What's been completed?
- What's in progress / blocked?
- Key decisions and WHY (not just what was chosen)
- Files read, created, modified
- Errors encountered and how resolved
- Dead ends explored (so the next session doesn't repeat them)

### 2. Gather current state

!`git status`

!`git diff --stat HEAD`

!`git log --oneline -5`

!`git branch --show-current`

Check if a plan exists for ongoing work:

!`ls .claude/plans/ 2>/dev/null`

### 3. Save the handoff as a Memory Domain memory

Call `mcp__ucis-kafka-mcp__create_memory` with:

- **`memory_type`**: `session` (or `milestone` if a major checkpoint was hit)
- **`importance`**: 0.7-0.9 (higher if the session crossed a meaningful boundary)
- **`content`**: structured handoff text, ~300-600 words covering:
  - Goal: 1-2 sentence summary of what we were working on
  - Completed: bulleted list of what landed
  - In Progress / Next Steps: bulleted list of what's queued, with file paths and specifics
  - Key Decisions: bullets of WHAT was chosen + WHY (so the next session doesn't reverse them)
  - Dead Ends: bullets of approaches tried that failed + why (so we don't repeat them)
  - Files Changed: list of paths touched, one line each
  - Current State: lint / tests / docker build / manual verification status
  - Hardware / Deploy State: workstation vs Jetson vs scope reachability (this is seestar-scope-specific — adapt for the project)
  - Context for Next Session: 2-4 sentences on the most important thing, biggest risk, what to do first
  - Recommended first action: exact command or step
- **`context_tags`**: include `["seestar-scope", "handoff", "<feature-area>"]` plus anything specific to the work
- **`foresight`**: `"Relevant when: <scenarios where this memory should resurface>"` — e.g., "Relevant when: continuing the gallery refactor, debugging the platesolve retry, picking up after the Jetson firmware update"
- **`perspective`**: a 2-3 sentence subjective lens on why this session mattered — what was learned, how it connects to bigger work

### 4. Confirm

After saving:

1. Print the returned `memory_id` (e.g., `memgraph_20260515_132750_575146`)
2. Suggest the next-session bootstrap:
   ```
   Say "Hey Data!!!" to surface recent memories, then /prime
   ```
3. If uncommitted changes exist, suggest `/commit` before ending the session

## Quality Criteria

A good handoff memory:

- Lets a fresh agent continue without asking clarifying questions
- Is concise (~300-600 words in `content`) — link to files rather than duplicating content
- Includes enough "why" context that the next agent makes the same decisions
- Explicitly lists dead ends to prevent wasted effort
- Has a concrete "first action" recommendation
- Has good `foresight` — so MAGMA retrieval surfaces it when the next session's context matches
- Has `perspective` — your subjective lens, not just facts

## Anti-patterns

- **NEVER** write `HANDOFF.md` or any other file as a substitute for `create_memory`. The CLAUDE.md / AGENTS.md memory-storage rules are explicit: ALL memories go to the Memory Domain.
- Don't include full file contents — reference paths instead
- Don't include conversation history or debug transcripts — summarize findings
- Don't be vague ("fix the gallery") — be specific ("fix the thumbnail proxy in `portal/backend/routers/gallery_onboard.py` — the `path` query param isn't URL-decoded before the scope HTTP fetch")
- Don't skip "Dead Ends" — this prevents the most common wasted effort
- Don't skip "Key Decisions" — without them the next agent may reverse your decisions
