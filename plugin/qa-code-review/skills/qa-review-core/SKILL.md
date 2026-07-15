---
name: qa-review-core
description: Framework-agnostic QA automation code-review standards. Always applied. Layered under a framework overlay (playwright-ts, playwright-js, selenium-java, bdd-cucumber) by the dispatcher. Defines severities, the scoring model, and the review/comment/fix contract shared by every framework.
---

# QA Automation Code Review — Core Standards

These rules apply to **every** QA automation framework. A framework overlay skill
adds language-specific rules on top; when both apply, findings from both are
merged. This file is the single source of truth consumed by the LLM reviewer,
the regex pre-pass (`review_runner.py`), and the provider adapters
(`CLAUDE.md`, `.github/copilot-instructions.md`).

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
   source. Use config/env/secret stores. Encrypted vault values are allowed. (High)
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

## Review / comment / fix contract

The agent runs three layers, in order:

- **Layer 1 — deterministic regex** (`review_runner.py`): fast, repo-specific
  anti-patterns. Never calls an LLM. Always runs.
- **Layer 2 — LLM semantic review**: reads the diff + the applicable skill(s),
  returns findings as JSON `{severity, file, line, rule, rationale, suggestion}`.
  Merged with Layer 1 findings; the union is scored and posted as **one PR/MR
  comment**.
- **Layer 3 — LLM auto-fix** (only when score < threshold and iteration < max):
  produces a minimal patch that resolves the findings, commits as the bot
  identity, pushes to the **same PR/MR source branch**, then re-runs Layer 1+2
  and posts a follow-up comment.

### Fix-loop guardrails (mandatory)

- `MAX_FIX_ITERATIONS` (default 3) — hard cap on fix rounds.
- Stop as soon as `score >= SCORE_THRESHOLD`.
- **Bot-author guard:** never trigger an auto-fix in response to a commit whose
  author is the bot itself — prevents an infinite review→fix→review loop.
- Change only what a finding requires; never reformat unrelated lines.

## Output rules for the LLM reviewer

- Return only findings you can tie to a specific added/changed line.
- Do not invent issues to pad the list. An empty finding set is a valid result.
- Keep every comment plain ASCII and actionable: what is wrong, why, and the fix.
