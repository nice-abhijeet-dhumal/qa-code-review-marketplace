# qa-code-review

Framework-agnostic QA automation **code review + auto-fix** agent, for
**GitHub and GitLab**. Reviews a PR/MR against composable framework
standards, posts a scored feedback comment, fixes the findings with an LLM,
pushes to the same branch, and re-reviews — with a deterministic, monotonic
guarantee.

## Overview

**Review has no LLM involvement at all.** Every skill (`qa-review-core` +
one driver overlay + `bdd-cucumber` when applicable) owns its own
`scripts/review.py`; the engine loads and merges them, and that is the
entire review step — deterministic, reproducible, and the sole source of
findings and the score.

1. **Detect** the framework(s) (root + immediate subdirectories, so `ui/`,
   `api/`-style monorepos are found) and compose the applicable skills.
2. **Review** — each active skill's `scripts/review.py`, merged. No LLM.
3. **Comment** — one scored review comment on the PR/MR.
4. **Fix** (the ONLY LLM step) — generate a fix, pass it through a
   **verify-before-commit gate** (rejects any fix that would not reduce
   Critical/High), commit as the bot, push to the same branch.
5. **Re-review** — repeat until the score clears the threshold or the
   iteration cap (max 3) is hit. Findings never increase between iterations.

## Frameworks (composable, auto-detected)

| Standard skill | Applies when |
|----------------|--------------|
| `qa-review-core` | always — universal rules + severity/scoring model |
| `playwright-ts` | `@playwright/test` + `tsconfig.json` |
| `playwright-js` | `@playwright/test`, no TypeScript |
| `selenium-java` | Maven/Gradle project with selenium |
| `bdd-cucumber` | any `*.feature` present (added on top of the driver overlay) |

## GitHub and GitLab, same entrypoint

`pr_review.py` auto-detects the platform (`GITHUB_ACTIONS`/`GITLAB_CI`/env
vars present) and uses the matching API for fetching changed files, the
head/source branch, and posting the comment.

## Dual fix engine (Claude or Copilot-family)

Set whichever you have — auto-chosen if `LLM_PROVIDER` is unset:

| Engine | Env | `LLM_PROVIDER` |
|--------|-----|----------------|
| Claude | `ANTHROPIC_API_KEY` | `claude` |
| GitHub Models (Copilot-family) | `GH_MODELS_TOKEN` | `github` |

With neither, the agent still runs the full deterministic review and
comments — it just cannot fix. Review quality is completely unaffected.

## Install

**Claude Code:**
```
/plugin marketplace add NiCE-AI-Marketplace/agentic-platform
/plugin install qa-code-review
```
Then invoke: `/plugin:qa-code-review`

**GitHub Copilot / OpenCode, or a TUI browser — via unagi:**
```bash
cd utils/unagi && ./install.sh
```

## Usage

Ask the agent, e.g.:
- "Review and fix PR #123" (GitHub) / "Review and fix MR !7" (GitLab)
- "Which standards apply to this repo?"
- "Review my local/staged changes"
- "Scan this repo" / "Review this commit"

See [agents/qa-code-review.agent.md](agents/qa-code-review.agent.md) for the full
Request → Script mapping, the Agent-flow and PR/MR-flow breakdown, and configuration.

## Guardrails (retries capped at 3, every level)

- **PR/MR-level**: `MAX_FIX_ITERATIONS` (default 3) review→fix→re-review rounds, stop at `SCORE_THRESHOLD` (default 80).
- **API/push-level**: `API_MAX_RETRIES` (default 3) for transient GitHub/GitLab API calls and the fix-commit push.
- **Agent-level**: the local Claude Code agent flow retries a failed detect→review→fix→push attempt up to 3 times total.
- **Bot-author guard** — never auto-fixes in response to the bot's own commit.
- **Verify-before-commit gate** — deterministic Critical/High can only decrease.

## Author

Abhijeet Dhumal ([@nice-abhijeet-dhumal](https://github.com/nice-abhijeet-dhumal))
