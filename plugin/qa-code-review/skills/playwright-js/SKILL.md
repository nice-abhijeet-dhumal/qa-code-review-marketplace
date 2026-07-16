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
| `scripts/review.py` | Deterministic patterns for the rules below (`CRITICAL_PATTERNS`, `HIGH_PATTERNS`, `MEDIUM_PATTERNS`, `LOW_PATTERNS`). Each pattern is a `Check(id, rule, suggestion, regex, scope, flags)` namedtuple -- the `id` (e.g. `PWJS-AWAIT`) is the stable identifier used throughout this doc. Merged with `qa-review-core/scripts/review.py` by `deterministic_review.py` when this overlay is selected (detected via `@playwright/test` in `package.json` with no `tsconfig.json`/`playwright.config.ts`). Review findings come only from this script — never from an LLM; `playwright-ts/scripts/review.py` re-exports these `Check` instances (filtered/extended by `id`) and adds the TS-only ones. |

## Critical

- **Missing `await` on Playwright actions** — no type checker will warn you.
  Flag any `page.goto/click/fill/check/selectOption/hover/press/type/
  setInputFiles/dragAndDrop` without `await` on the line. (`PWJS-AWAIT`)
- **Missing `await` on `waitForResponse`/`waitForRequest`/`waitForEvent`/
  `waitForURL`/`waitForFunction`** — a dropped wait promise races ahead of the
  event. Await it, assign it for a later await, or use `Promise.all([...])`
  with the triggering action (both recognized as handled). (`PWJS-AWAIT-EVENT`)
- **`page.pause()`** committed — hangs CI. (`CORE-3`, from qa-review-core)
- **`waitForTimeout(>= 1000)`** in specs — use `expect(locator).toBeVisible()`. (`CORE-2`, from qa-review-core)
- **Nested `test()`** inside another `test()` body — handled as a shared,
  engine-level check (`PW-NESTED-TEST`) in `deterministic_review.py`, not a
  regex in this file.

## High

- **Locators in spec files** — POM violation. (`CORE-9`, from qa-review-core)
- **Value assertions in page objects** — move to spec. (`CORE-9`, from qa-review-core)
- **Fragile locators:** `.nth(0)`, `:first-child`, absolute XPath, dynamic IDs. (`CORE-11`, from qa-review-core)
- **Deprecated APIs:** `$()`/`$$()` (`PWJS-DOLLAR-API`), `page.waitForSelector()`
  (`PWJS-WAIT-SELECTOR`), `$eval()`/`$$eval()` (`PWJS-DOLLAR-EVAL`).
- **`page.waitForNavigation()` without `Promise.all`.** (`PWJS-WAIT-NAV`)
- **`beforeAll` with the page fixture** — shared state across workers. (`PWJS-BEFOREALL-PAGE`)
- **`page.evaluate()` with hardcoded JS or an inline arrow function** —
  bypasses auto-retry; use locator actions. (`PWJS-EVALUATE-HARDCODED`)
- **`waitForLoadState('networkidle')`** — flaky/discouraged; assert on
  visible UI state instead. (`PWJS-NETWORKIDLE`)
- **`{ force: true }`** on `click`/`fill`/`check`/`selectOption`/etc. —
  bypasses actionability checks and masks real UI defects; remove it and fix
  the root cause, or justify it in a comment with a ticket. (`PWJS-FORCE-TRUE`)
- **Non-retrying assertion on a locator method**
  (`expect(await locator.textContent())`) — bypasses web-first auto-retry; use
  `expect(locator).toHaveText(x)` instead. Distinct from the Medium
  page-level-getter case below (mutually exclusive, never both fire on the
  same line). (`PWJS-NONRETRY-LOCATOR`)
- **Hardcoded test data in a spec file** (`page.fill`/`.type` with a literal
  string) — use test data or config instead. (`PWJS-HARDCODE-DATA`)
- **Playwright test framework imported without a `Page`/`Locator` type** in a
  page object file — verify this import is actually needed there. (`PWJS-PW-IMPORT`)

## Medium

- **`page.reload()` without a follow-up assertion.** (`PWJS-RELOAD-NOASSERT`)
- **Debug `console.log`** left in code. (`CORE-10`, from qa-review-core)
- **Always-on `page.screenshot()`** — gate behind failure hooks. (`PWJS-SCREENSHOT-ALWAYS`)
- **`page` passed as a parameter to a helper function** — consider a fixture
  or POM method instead. (`PWJS-PAGE-PARAM`)
- **`await` inside `expect()`** for a page-level getter
  (`expect(await page.title())`) — hoist the await:
  `const val = await page.title(); expect(val)...`. Distinct from the High
  locator-method case above. (`PWJS-EXPECT-AWAIT-GETTER`)

## Low

- `test.only` / `describe.only` committed. (`PWJS-TEST-ONLY`)
- Missing `@tag` annotations. (`PWJS-NO-TAG`)
- `test.setTimeout()` inside a test — set the timeout globally in
  `playwright.config.js` instead. (`PWJS-SET-TIMEOUT`)
- `page.fill(selector, value)` — the older API; prefer `locator.fill()`. (`PWJS-FILL-OLD-API`)
- Empty or missing `describe()` label. (`PWJS-DESCRIBE-EMPTY`)
- **Non-descriptive test titles** (`test('test1', ...)`, `test('works', ...)`)
  — name the behaviour under test so reports/failures read clearly. Shared,
  engine-level check (`PW-NONDESC-TITLE`) in `deterministic_review.py`, not a
  regex in this file (needs a denylist lookup a single regex can't express).
- `getByRole`/`getByTestId`/`getByText`/`getByLabel`/`getByPlaceholder`/
  `getByAltText`/`getByTitle` — consider `page.locator()` with a CSS selector
  per this repo's locator strategy. (`PWJS-GETBYROLE`, `PWJS-GETBYTESTID`,
  `PWJS-GETBYTEXT`, `PWJS-GETBYLABEL`, `PWJS-GETBYPLACEHOLDER`,
  `PWJS-GETBYALTTEXT`, `PWJS-GETBYTITLE`)

> **Not currently automated:** missing/incorrect JSDoc types (where a project
> relies on `// @ts-check` or JSDoc for editor safety) requires type-level
> reasoning the regex engine can't do. Treat as manual-review guidance, not a
> pipeline check.

## Conventions

- Test files end in `.spec.js` (or `.spec.mjs`) so the runner discovers them.
- Locators in page objects under `pages/` or `page-objects/`; data in fixtures/config.
