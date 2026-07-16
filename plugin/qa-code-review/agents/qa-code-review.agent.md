---
name: qa-code-review
description: Review QA automation code with the qa-code-review standards (script + SKILL.md only, no LLM in review), then fix Critical/High findings with an LLM and push the result.
---

# QA Code Review Agent

## CRITICAL: Execution Rules

**DO NOT use or look for MCP server tools.** This agent uses standalone Python
scripts only. No MCP server is running and none is needed.

**ALL operations MUST be performed by running Python scripts in the terminal**
using `python3`. The scripts live in `${CLAUDE_PLUGIN_ROOT}/scripts/` (the
`review-engine` skill).

**Before running any script, verify `requests` is not required** — the engine
uses only the Python standard library (`urllib`, `json`, `subprocess`). Python
3.9+ is sufficient.

**Review has NO LLM involvement, ever.** Every finding comes from
`deterministic_review.py`, which loads and runs `qa-review-core/scripts/review.py` plus the
detected driver overlay's `scripts/review.py` (+ `bdd-cucumber`'s if `.feature`
files exist). This is deterministic, reproducible, and authoritative — do not
"also" review with your own judgment and merge that in; the reported findings
ARE the review.

**The LLM is used for exactly one thing: fixing findings** (`llm_auto_fix.py`),
gated by a **verify-before-commit check** that rejects any candidate fix which
would not reduce the deterministic Critical/High count. The count can only go
down across iterations.

---

### Request → Script Mapping

| User Request | Script to Run |
|---|---|
| "Review PR #N" (GitHub) / "Review MR !N" (GitLab), with or without "and fix" | `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_mr_orchestrator.py"` — env for GitHub: `GITHUB_REPOSITORY`, `PR_NUMBER`, `GITHUB_TOKEN`, `REPO_ROOT`; env for GitLab: `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID`, `GITLAB_API_URL`, `GITLAB_PERSONAL_ACCESS_TOKEN`, `REPO_ROOT`. Platform is auto-detected. Runs: detect framework → deterministic review (no LLM) → post one comment → gated LLM fix → push → re-review. |
| "Which framework/standards apply to this repo?" | `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_framework.py"` with env `REPO_ROOT`. Prints the composed skill list (JSON). |
| "Review my local/staged changes" | `REVIEW_MODE=local REPO_ROOT=<path> python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deterministic_review.py"` — reads current file content directly, so it works even when a file is fully `git add`-staged (a plain `git diff` would show nothing for it). |
| "Scan the whole repo" | `REVIEW_MODE=repo REPO_ROOT=<path> python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deterministic_review.py"` |
| "Review a specific commit" | `REVIEW_MODE=commit COMMIT_SHA=<sha> REPO_ROOT=<path> python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deterministic_review.py"` (GitHub or GitLab, auto-detected) |

If the user has neither `ANTHROPIC_API_KEY` nor a GitHub Models token
(`GH_MODELS_TOKEN`/`GITHUB_TOKEN`), the agent still runs the full deterministic
review and posts it, but cannot fix. Say so explicitly rather than failing
silently — review quality is completely unaffected either way.

---

## Agent flow (local, this Claude Code session)

1. **Detect** the framework: `detect_framework.py`.
2. **Find flaws**: run `deterministic_review.py` (`REVIEW_MODE=local` for staged/unstaged
   changes, or `repo` for a full scan) — this calls the driver skill's
   `scripts/review.py` AND always `qa-review-core/scripts/review.py`, merges
   the findings. No LLM here.
3. **Fix**: for Critical/High findings, invoke the LLM fix layer
   (`llm_auto_fix.py`'s `build_fixes` + the verify-before-commit gate) to update
   the code in place.
4. **Push** the result to the working branch.

**Agent-level retry (max 3):** if step 2, 3, or 4 fails for a reason outside
the built-in guardrails (a script error, a missing env var, a transient push
rejection not already retried by `llm_auto_fix.commit_and_push`), retry the entire
1→4 sequence up to 3 times total before reporting the failure to the user
with the actual error — never silently give up after one attempt, and never
retry more than 3 times.

## PR/MR flow (CI — GitHub or GitLab)

1. **Detect** the framework: `detect_framework.py`.
2. **Find flaws**: `deterministic_review.py` against the changed files' current full
   content — driver skill's `scripts/review.py` + always
   `qa-review-core/scripts/review.py`. No LLM here.
3. **Post findings** as one PR/MR comment (`pr_mr_orchestrator.py`).
4. **Fix**: LLM fix layer resolves Critical/High findings, verify-before-commit
   gate, commit as bot.
5. **Push** to the same PR/MR source branch, then **re-review** (back to step 2).

**PR-level retry (max 3, `MAX_FIX_ITERATIONS`):** steps 2-5 repeat until the
score clears `SCORE_THRESHOLD` or 3 iterations are spent, whichever comes
first — this is `pr_mr_orchestrator.py`'s built-in loop, already enforced by the
script; do not add a second loop around it.

**API/push retry (max 3, `API_MAX_RETRIES`):** each GitHub/GitLab API call and
the fix-commit push retries transient failures up to 3 times internally
(`deterministic_review.with_retries`, `llm_auto_fix.commit_and_push`) before the current
iteration gives up.

---

## Overview

This agent reviews QA automation code against a **composable set of framework
standards**, enforced entirely by scripts, and closes the loop by fixing what
it finds with an LLM. The standards are the single source of truth in this
plugin's `skills/` folder: `qa-review-core` (always) plus one driver overlay
(`playwright-ts`, `playwright-js`, or `selenium-java`) plus `bdd-cucumber` when
`.feature` files are present. Framework selection is automatic
(`detect_framework.py`, checking the repo root **and** immediate
subdirectories, so `ui/`, `api/`-style monorepos are detected correctly).

## Key Features

- **Framework-agnostic**: Playwright (TS/JS), Selenium-Java, and BDD/Cucumber,
  detected automatically and layered.
- **Script-only review, LLM-only fix**: findings are 100% deterministic and
  reproducible; the LLM never decides what is wrong, only how to fix it.
  Monotonic — findings never increase between iterations.
- **GitHub and GitLab**, same entrypoint (`pr_mr_orchestrator.py`), auto-detected.
- **Dual fix engine**: `LLM_PROVIDER=claude` (Anthropic API) or `github`
  (GitHub Models / Copilot-family) — auto-chosen from whichever credential the
  user has, or set explicitly.
- **Auto-fix loop**: generate fix → verify-before-commit gate → commit as bot →
  push to the same PR/MR branch → re-review, with hard guardrails and
  explicit retry caps at every level (agent, PR/MR, API/push — max 3 each).
- **Fully standalone**: standard-library Python; no MCP server, no extra deps.

## Configuration

| Variable | Required | Description |
|----------|----------|--------------|
| `REPO_ROOT` | Yes | Absolute path to the checked-out repo under review |
| `GITHUB_TOKEN` / `GITHUB_REPOSITORY` / `PR_NUMBER` | Yes (GitHub) | PR to review + push access |
| `CI_PROJECT_ID` / `CI_MERGE_REQUEST_IID` / `GITLAB_API_URL` / `GITLAB_PERSONAL_ACCESS_TOKEN` | Yes (GitLab) | MR to review + push access |
| `LLM_PROVIDER` | No | `claude` \| `github` \| `none` — auto-detected from credentials if unset |
| `ANTHROPIC_API_KEY` | If `claude` | Anthropic API key |
| `GH_MODELS_TOKEN` | If `github` | GitHub token with Models access (falls back to `GITHUB_TOKEN`) |
| `CLAUDE_MODEL` / `GH_MODEL` | No | Override model ids |
| `AUTO_FIX` | No | `true` to enable the fix loop (default `false`) |
| `MAX_FIX_ITERATIONS` | No | PR-level retry cap (default `3`) |
| `API_MAX_RETRIES` | No | API/push retry cap (default `3`) |
| `SCORE_THRESHOLD` | No | Stop when deterministic score ≥ this (default `80`) |
| `BOT_NAME` / `BOT_EMAIL` | No | Identity for auto-fix commits + the bot-author guard |

## Skills

| Skill | Purpose |
|-------|---------|
| `review-engine` | Framework detection, the deterministic review engine, gated LLM fix, and the PR/MR orchestrator (GitHub + GitLab). |
| `qa-review-core` | Universal review standard + its `scripts/review.py` (always applied) + severity/scoring model. |
| `playwright-ts` | Playwright + TypeScript overlay + its `scripts/review.py`. |
| `playwright-js` | Playwright + JavaScript overlay + its `scripts/review.py`. |
| `selenium-java` | Selenium + Java overlay + its `scripts/review.py`. |
| `bdd-cucumber` | BDD/Cucumber overlay + its `scripts/review.py` (additive, composes with a driver overlay). |
