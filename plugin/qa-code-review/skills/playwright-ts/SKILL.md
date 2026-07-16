---
name: playwright-ts
description: Playwright + TypeScript review overlay. Applied on top of qa-review-core when the repo uses @playwright/test with TypeScript (package.json has @playwright/test and a tsconfig.json is present). Covers await semantics, locator strategy, POM rules, and TS type-safety specifics.
---

# Playwright + TypeScript — Review Overlay

Applied together with `qa-review-core`. Rules below are additional or refine a
core rule for this stack.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/review.py` | Deterministic patterns for the rules below. Imports `playwright-js/scripts/review.py` (identical runtime API) and adds the TypeScript-only patterns (`any`/`as any`, typed helper params). Merged with `qa-review-core/scripts/review.py` by `deterministic_review.py` when this overlay is selected (detected via `@playwright/test` + `tsconfig.json`/`playwright.config.ts`). Review findings come only from this script — never from an LLM. |

## Critical

- **Missing `await` on Playwright actions.** `page.goto/click/fill/check/
  selectOption/hover/press/type/setInputFiles` etc. return promises; without
  `await` they silently no-op and create race conditions.
- **`page.pause()`** committed — launches the Inspector and hangs CI forever.
- **`waitForTimeout(>= 1000)`** in spec/test files — replace with
  `expect(locator).toBeVisible()` or `locator.waitFor()`. (In a page object,
  short stabilization waits are downgraded to Medium but still discouraged.)
- **Nested `test()` inside another `test()` body** — Playwright throws at
  runtime. Note: `test()` inside `test.describe()` is valid and must NOT flag.

## High

- **Locators in spec files** (`page.locator(...)` in a `.spec.ts`) — POM
  violation; move to a page object and expose a method.
- **Value assertions in page objects** (`toBe`, `toEqual`, `toContain`,
  `toBeTruthy`, `toHaveCount`, ...) — move to the spec. `toBeVisible/
  toBeHidden/toBeEnabled` are allowed as auto-waits.
- **Fragile locators:** `.nth(0)`, `:first-child`, absolute XPath
  (`//div/div/div[...]`), auto-generated IDs (`react-select-3-...`).
- **Deprecated APIs:** `$()`, `$$()`, `page.waitForSelector()` — prefer
  `page.locator()` + `expect(...).toBeVisible()`.
- **`page.waitForNavigation()` without `Promise.all([...])`** — race condition.
- **`beforeAll(async ({ page }) => ...)`** — page fixture in `beforeAll` shares
  state across workers; use `beforeEach` or a fixture.
- **`page.evaluate()` with hardcoded JS** — bypasses auto-retry; use locator actions.

## Medium

- **TypeScript `any` / `as any`** — defeats type safety; use specific types.
- **`page.reload()` without a follow-up assertion** — verify page state after.
- **Always-on `page.screenshot()`** — gate behind failure hooks.
- **`await` inside `expect()`** for async getters (`expect(await page.title())`)
  — hoist the await: `const t = await page.title(); expect(t)...`.

## Low (insights, non-blocking)

- `test.only` / `describe.only` committed — blocks the rest of the suite.
- Test missing a `@tag` annotation — harder to filter in CI.
- `test.setTimeout()` inside a test — prefer a global setting in the config.

## Conventions

- Test files must end in `.spec.ts` so the runner discovers them.
- Page objects under `src/ui/pages/`; test data in `testdata/` or config, not inline.
