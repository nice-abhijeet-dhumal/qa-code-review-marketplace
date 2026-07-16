---
name: qa-review-core
description: Framework-agnostic QA automation code-review standards. Always applied. Layered under a framework overlay (playwright-ts, playwright-js, selenium-java, bdd-cucumber) by the dispatcher. Defines severities, the scoring model, and the review/comment/fix contract shared by every framework.
---

# QA Automation Code Review — Core Standards

These rules apply to **every** QA automation framework. A framework overlay skill
adds language-specific rules on top; when both apply, findings from both are
merged. This file documents the standard; `scripts/review.py` is what actually
enforces it — **review findings come from that script alone, never from an
LLM.** An LLM is only ever used downstream, to fix findings this script (and
the active driver overlay's script) already reported.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/review.py` | Deterministic patterns for the universal rules below (`CRITICAL_PATTERNS`, `HIGH_PATTERNS`, `MEDIUM_PATTERNS`, `LOW_PATTERNS`). Loaded and merged with the active driver overlay's own `scripts/review.py` by `review-engine`'s `engine.py`. Always loaded, regardless of detected framework. |

## Severity model

| Severity | Meaning | Score impact |
|----------|---------|--------------|
| Critical | Breaks tests, hangs CI, or ships a secret | -15 |
| High     | Flaky, unreliable, or violates a core pattern | -7 |
| Medium   | Maintainability / debug leftovers | -3 |
| Low      | Style / advisory insight | -1 |

Score starts at 100. Verdict: `>=90` Approve, `75-89` Approve with comments,
`50-74` Request changes, `<50` Block. **Any Critical or High blocks merge.**

## Universal rules (all frameworks)

1. **No swallowed errors.** Empty `catch {}` blocks hide real failures. (Critical)
2. **No hardcoded/blind sleeps.** Fixed waits (`sleep`, `waitForTimeout`,
   `Thread.sleep`) are flaky. Use explicit waits / auto-retrying assertions. (Critical for >1s, Medium otherwise)
3. **No committed debugger/pause calls** that hang CI (`page.pause()`,
   `debugger;`, breakpoints). (Critical)
4. **No real assertions commented out.** A disabled assertion is a silent gap. (Critical)
5. **No empty test bodies.** A test with no steps passes meaninglessly. (Critical)
6. **No hardcoded secrets.** Passwords, tokens, API keys, or credentials in
   source. Use config/env/secret stores. Encrypted vault values are allowed. (Critical)
7. **No hardcoded environment URLs** in test/page code — import from config. (High)
8. **Skipped tests need a ticket reference** (e.g. `LV-1234`, `JIRA-xxx`) in a
   comment, so the skip is tracked. (High)
9. **Page Object Model boundaries.** Locators live in page objects, never in
   specs. Value assertions (business expectations) live in specs, never in page
   objects. Visibility/enabled waits inside page objects are allowed. (High)
10. **No debug leftovers** (`console.log`, `System.out.println`, print). (Medium)
11. **No fragile locators** — index-based (`nth(0)`, `:first-child`),
    absolute XPath, or auto-generated dynamic IDs. Prefer stable attributes. (High)
12. **Track TODO/FIXME/HACK** with a ticket reference. (Low)

## Review / fix contract

- **Review (deterministic, no LLM):** `engine.py` detects the framework, loads
  `qa-review-core/scripts/review.py` + the active driver overlay's
  `scripts/review.py` (+ `bdd-cucumber`'s if `.feature` files exist), runs
  every pattern against the changed files, and posts **one** comment. This is
  the entire review step — reproducible, and the sole source of findings and
  the score.
- **Fix (LLM, only step where an LLM runs):** when auto-fix is enabled and the
  score is below `SCORE_THRESHOLD`, `llm_fix.py` asks the LLM (Claude or
  GitHub Models, whichever the user has access to) to resolve the findings,
  applies a **verify-before-commit gate** (re-runs the deterministic review on
  the candidate and rejects any fix that does not reduce Critical/High),
  commits as the bot identity, and pushes to the **same PR/MR source branch**.
  The loop then re-reviews.

### Retry guardrails (mandatory, max 3 each)

- **PR-level retry** (`MAX_FIX_ITERATIONS`, default 3): hard cap on
  review→fix→re-review rounds for a single PR/MR.
- **API/push retry** (`API_MAX_RETRIES`, default 3): transient GitHub/GitLab
  API calls and the fix-commit push are retried up to 3 times before the
  iteration gives up.
- **Agent-level retry** (local Claude Code agent flow, max 3): if the whole
  detect → review → fix → push attempt fails for a reason not covered above
  (script error, environment misconfiguration), the agent retries the entire
  attempt up to 3 times total before reporting failure to the user. See
  `agents/qa-code-review.agent.md`.
- Stop as soon as `score >= SCORE_THRESHOLD`.
- **Bot-author guard:** never trigger an auto-fix in response to a commit whose
  author is the bot itself — prevents an infinite review→fix→review loop.
- Change only what a finding requires; never reformat unrelated lines.
