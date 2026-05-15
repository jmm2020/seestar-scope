---
description: Create an atomic commit for current changes
---

# Commit Changes

## Process

### 1. Review changes

!`git status`

!`git diff --stat HEAD`

!`git ls-files --others --exclude-standard`

### 2. Stage files

Add the untracked and changed files relevant to the current work. Be deliberate — do not run `git add -A` blindly.

**Do NOT stage:**
- `.env` or any credential file
- `cloudflared/*.json` (gitignored already, but double-check)
- Large binaries
- Files unrelated to the current task
- `tmp/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` (gitignored, should be fine)

### 3. Create the commit

Use conventional commit tags:

- `feat:` — New capability or feature
- `fix:` — Bug fix
- `refactor:` — Code restructure without behavior change
- `docs:` — Documentation only
- `test:` — Test additions or fixes
- `chore:` — Build, CI, tooling, dependency bumps
- `perf:` — Performance improvement

**Scope** is the **domain area or feature group**, not a layer name. Real scopes from `git log -30`:

- `(gallery)` — onboard or session gallery work
- `(imaging)` — `views/imaging.py`, MJPEG, exposure controls, enhancement panel
- `(alpaca)` — `AlpacaClient`, native :32323 channel work
- `(imager)` — `:4800` TCP stacked-frame path (`SeestarImagerClient`)
- `(observer)` — `:4701` guest JSON-RPC (`SeestarObserverClient`)
- `(slew)` — goto / slew helpers
- `(seestar-alp)` — bridge container or `alp-config/`
- `(portal)` — cross-cutting portal changes
- `(autofocus)` — autofocus router/service
- `(docker)` — `docker-compose.yml`, Dockerfiles
- `(sessions)` — session DB or session-management routers
- `(conditions)` — sky-conditions router/service
- `(docs)` — `docs/`, `README.md`
- `(ci)` — `.github/workflows/`

If your change crosses domains, pick the dominant one and mention the rest in the body. Don't invent new scopes without precedent in `git log`.

**Commit message format:**

```
tag(scope): concise description of what changed

[Optional body explaining WHY this change was made,
not just what. Include context that isn't obvious from
the diff — constraints, prior incidents, design intent.]

[Optional: Fixes #123, Closes #456]
```

**Never include "claude code" or AI attribution in commit messages.** This is a personal-project convention.

### 4. Capture AI Layer changes

If this commit touches `.claude/` or `CLAUDE.md` or `AGENTS.md`, add a `Context:` section to the body:

```
feat(autofocus): add platesolve retry with exponential backoff

The previous single-attempt platesolve failed silently on transient
network blips. Three retries with backoff gives ~95% reliability
without hanging the UI.

Context:
- Updated CLAUDE.md "FIRMWARE 7.34 AUTHENTICATION" — note that
  platesolve uses native ALPACA :32323, not the gated :4700
- Added .claude/commands/debug-platesolve.md for failure inspection

Fixes #123
```

**Why this matters:** `git log` is the long-term memory of the project. Future agents read it to understand WHY a rule or command exists. If AI Layer changes aren't captured, the evolution becomes invisible.

### 5. Verify

!`git log -1 --stat`

Confirm the commit landed and the staged files are exactly what you intended. If anything is wrong, **do not** amend silently — say so, and either fix-forward with a follow-up commit or ask the user before amending.
