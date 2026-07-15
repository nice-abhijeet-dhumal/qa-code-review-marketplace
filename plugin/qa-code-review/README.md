# qa-code-review

Framework-agnostic QA automation **code review + auto-fix** agent. Reviews a
PR/MR against composable framework standards, posts a scored feedback comment,
auto-fixes the findings, pushes to the same branch, and re-reviews — with a
deterministic, monotonic guarantee.

## Overview

The agent runs a two-layer review and closes the loop:

1. **Detect** the framework(s) and compose the applicable standards.
2. **Review** — Layer 1 deterministic regex (authoritative, reproducible) +
   Layer 2 LLM semantic (advisory; Claude or GitHub Models).
3. **Comment** — one scored review comment on the PR/MR.
4. **Auto-fix** — generate a fix, pass it through a **verify-before-commit gate**
   (rejects any fix that would not reduce Critical/High), commit as the bot,
   push to the same branch.
5. **Re-review** — repeat until the score clears the threshold or the iteration
   cap is hit. Findings never increase between iterations.

## Frameworks (composable, auto-detected)

| Standard skill | Applies when |
|----------------|--------------|
| `qa-review-core` | always — universal rules + severity/scoring model |
| `playwright-ts` | `@playwright/test` + `tsconfig.json` |
| `playwright-js` | `@playwright/test`, no TypeScript |
| `selenium-java` | Maven/Gradle project with selenium |
| `bdd-cucumber` | any `*.feature` present (added on top of the driver overlay) |

## Dual engine (Claude or Copilot-family)

Set whichever you have — the engine is selected per run:

| Engine | Env | `LLM_PROVIDER` |
|--------|-----|----------------|
| Claude | `ANTHROPIC_API_KEY` | `claude` |
| GitHub Models (Copilot-family) | `GH_MODELS_TOKEN` | `github` |

With neither, the agent runs Layer 1 (regex) only and comments — no LLM review or fix.

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
- "Review and fix PR #123" (GitHub)
- "Which standards apply to this repo?"
- "Run a Layer-1 regex scan of this repo"

See [agents/qa-code-review.agent.md](agents/qa-code-review.agent.md) for the full
Request → Script mapping and configuration.

## Guardrails

- `MAX_FIX_ITERATIONS` (default 3), stop at `SCORE_THRESHOLD` (default 80).
- **Bot-author guard** — never auto-fixes in response to the bot's own commit.
- **Verify-before-commit gate** — deterministic Critical/High can only decrease.

## Author

Abhijeet Dhumal ([@nice-abhijeet-dhumal](https://github.com/nice-abhijeet-dhumal))
