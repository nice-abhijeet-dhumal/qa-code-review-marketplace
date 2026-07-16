---
name: playwright-js
description: Playwright + JavaScript review overlay. Applied on top of qa-review-core when the repo uses @playwright/test without TypeScript (package.json has @playwright/test, no tsconfig.json, sources are .js/.mjs). Same runtime rules as playwright-ts minus the TypeScript type checks.
---

# Playwright + JavaScript — Review Overlay

Applied together with `qa-review-core`. Runtime behaviour matches Playwright-TS;
the difference is no compiler safety net, so async and locator mistakes are
easier to ship and matter more.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/review.py` | Deterministic patterns for the rules below (`CRITICAL_PATTERNS`, `HIGH_PATTERNS`, `MEDIUM_PATTERNS`, `LOW_PATTERNS`). Merged with `qa-review-core/scripts/review.py` by `deterministic_review.py` when this overlay is selected (detected via `@playwright/test` in `package.json` with no `tsconfig.json`/`playwright.config.ts`). Review findings come only from this script — never from an LLM; `playwright-ts/scripts/review.py` re-exports these patterns and adds the TS-only ones. |

## Critical

- **Missing `await` on Playwright actions** — no type checker will warn you.
  Flag any `page.goto/click/fill/check/selectOption/hover/press/type` without
  `await` on the line.
- **`page.pause()`** committed — hangs CI.
- **`waitForTimeout(>= 1000)`** in specs — use `expect(locator).toBeVisible()`.
- **Nested `test()`** inside another `test()` body.

## High

- **Locators in spec files** — POM violation.
- **Value assertions in page objects** — move to spec.
- **Fragile locators:** `.nth(0)`, `:first-child`, absolute XPath, dynamic IDs.
- **Deprecated APIs:** `$()`, `$$()`, `page.waitForSelector()`.
- **`page.waitForNavigation()` without `Promise.all`.**
- **`beforeAll` with the page fixture** — shared state across workers.

## Medium

- **Missing/incorrect JSDoc types** where the project relies on `// @ts-check`
  or JSDoc for editor safety.
- **`page.reload()` without a follow-up assertion.**
- **Debug `console.log`** left in code.

## Low

- `test.only` / `describe.only` committed.
- Missing `@tag` annotations.

## Conventions

- Test files end in `.spec.js` (or `.spec.mjs`) so the runner discovers them.
- Locators in page objects under `pages/` or `page-objects/`; data in fixtures/config.
