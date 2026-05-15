---
description: Meta — generate a new slash command following seestar-scope patterns
argument-hint: <command-name> <purpose description>
---

# Create Command

## Objective

Create a new slash command: `$ARGUMENTS`

You're an agent creating a command for another agent (which may be you in the next session). Write instructions you'd want to receive.

## Context

Existing commands: !`ls .claude/commands/`

Reference patterns:
- @.claude/commands/plan-feature.md (multi-phase workflow)
- @.claude/commands/commit.md (single-step action)
- @.claude/commands/prime.md (context loader)

Project conventions: @CLAUDE.md

## Process

### 1. Parse the request

- **Command name**: first arg, kebab-case
- **Purpose**: remaining args
- **Type**: classify

| Type | Pattern | Examples |
|---|---|---|
| WORKFLOW | Multi-phase, produces an artifact, may dispatch subagents | `/plan-feature`, `/handoff` |
| ACTION | Single operation, immediate result | `/commit`, `/deploy` |
| CONTEXT | Loads state into the conversation | `/prime`, `/prime-backend` |
| DIAGNOSTIC | Investigates a system, produces a report | `/debug-scope`, `/validate` |

Decide:
- Does it need arguments? → add `argument-hint`
- Does it produce a file? → define the output path (use `.claude/plans/`, `HANDOFF.md`, or `tmp/<area>/`)
- Does it need subagents? → mention `Task` tool with `subagent_type`
- Does it need bash / file refs? → use `!`command`` and `@file` for runtime expansion

### 2. Explore existing patterns

Pick the closest existing command to your new one. Read it in full. Mirror its structure — frontmatter, section headers, output format.

If there isn't a close match, default to the `plan-feature.md` template for WORKFLOW, `commit.md` for ACTION, `prime.md` for CONTEXT.

### 3. Generate the command file

Write to `.claude/commands/<name>.md` using this skeleton:

```markdown
---
description: {one-sentence description that shows up in `/` autocomplete}
argument-hint: {only if it takes args}
---

# {Title}

## Objective

{What this command does, and why it exists. Be concrete.}

## Process

### 1. {First step}

{Steps with !`bash commands` and @file references inlined.}

### 2. {Next step}

...

## Output

{What gets produced — file path, console report, or both. Show the structure if there's a template.}
```

### 4. Self-check

Before writing, mentally walk through executing the command:

- Is every step explicit? Or are there gaps a fresh agent would have to guess at?
- Does it only ask for things Claude Code can actually do? (Read, Edit, Write, Bash, Task with subagents, WebSearch, WebFetch)
- Does it match seestar-scope's stack? (Python/ruff/pytest, not Bun/tsc/eslint)
- Is the complexity appropriate? Simple actions get simple commands — don't over-engineer.
- Does it cite the right hosts? (Workstation source-only, Jetson runtime, scope at .132)

### 5. Report

After writing, output:

```
## Command Created

**File**: `.claude/commands/{name}.md`
**Usage**: `/{name} {args if any}`
**Type**: {WORKFLOW/ACTION/CONTEXT/DIAGNOSTIC}

**What it does**: {one-line}

**Try it**: `/{name}` to verify it does what you expect.
```

Then suggest `/commit` to capture the new command in `git log` with a `chore(ai):` scope (see commit.md for the AI-Layer capture pattern).
