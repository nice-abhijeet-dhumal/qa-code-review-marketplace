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
- **`page.evaluate()` with hardcoded JS or an inline arrow function** —
  bypasses auto-retry; use locator actions.
- **Hardcoded test data in a spec file** (`page.fill`/`.type` with a literal
  string) — use test data or config instead.
- **Playwright test framework imported without a `Page`/`Locator` type** in a
  page object file — verify this import is actually needed there.

## Medium

- **`page.reload()` without a follow-up assertion.**
- **Debug `console.log`** left in code.
- **Always-on `page.screenshot()`** — gate behind failure hooks.
- **`page` passed as a parameter to a helper function** — consider a fixture
  or POM method instead.
- **`await` inside `expect()`** for async getters
  (`expect(await page.title())`) — hoist the await:
  `const val = await page.title(); expect(val)...`.

## Low

- `test.only` / `describe.only` committed.
- Missing `@tag` annotations.
- `test.setTimeout()` inside a test — set the timeout globally in
  `playwright.config.js` instead.
- `page.fill(selector, value)` — the older API; prefer `locator.fill()`.
- Empty or missing `describe()` label.
- `getByRole`/`getByTestId`/`getByText`/`getByLabel`/`getByPlaceholder`/
  `getByAltText`/`getByTitle` — consider `page.locator()` with a CSS selector
  per this repo's locator strategy.

> **Not currently automated:** missing/incorrect JSDoc types (where a project
> relies on `// @ts-check` or JSDoc for editor safety) requires type-level
> reasoning the regex engine can't do. Treat as manual-review guidance, not a
> pipeline check.

## Conventions

- Test files end in `.spec.js` (or `.spec.mjs`) so the runner discovers them.
- Locators in page objects under `pages/` or `page-objects/`; data in fixtures/config.
