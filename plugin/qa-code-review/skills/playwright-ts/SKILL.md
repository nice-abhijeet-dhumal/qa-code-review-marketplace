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
  selectOption/hover/press/type/setInputFiles/dragAndDrop/dragTo/focus` etc.
  return promises; without `await` they silently no-op and create race
  conditions.
- **`await` on a locator *creation* with no chained action** (e.g.
  `await page.locator('#x');` with nothing after it) — locators are lazy;
  awaiting the creation itself instead of an action on it is a logic error.
- **Conditional assertion guarded by `isVisible`/`isEnabled`/etc.**
  (`if (await locator.isVisible()) { await expect(...) }`) — the branch may
  never run, letting the test pass vacuously.
- **`test.setTimeout(0)`** — disables the timeout globally, masking flakiness
  instead of fixing the root cause.
- **`page.pause()`** committed — launches the Inspector and hangs CI forever.
- **`waitForTimeout(>= 1000)`** in spec/test files — replace with
  `expect(locator).toBeVisible()` or `locator.waitFor()`. (In a page object,
  short stabilization waits are downgraded to Medium but still discouraged.)
- **Nested `test()` inside another `test()` body** — Playwright throws at
  runtime. Note: `test()` inside `test.describe()` is valid and must NOT flag.

## High

- **`test.only` / `describe.only` committed** — silently skips the rest of
  the suite in CI; remove before merging.
- **Locators in spec files** (`page.locator(...)` in a `.spec.ts`) — POM
  violation; move to a page object and expose a method.
- **Value assertions in page objects** (`toBe`, `toEqual`, `toContain`,
  `toBeTruthy`, `toHaveCount`, ...) — move to the spec. `toBeVisible/
  toBeHidden/toBeEnabled` are allowed as auto-waits.
- **Fragile locators:** `.nth(0)`, `:first-child`, `.first()` (verify the set
  is genuinely ordered/unique), absolute XPath (`//div/div/div[...]`),
  auto-generated IDs (`react-select-3-...`).
- **Deprecated APIs:** `$()`, `$$()`, `$eval()`, `$$eval()`,
  `page.waitForSelector()` — prefer `page.locator()` + locator methods +
  `expect(...).toBeVisible()`.
- **`page.waitForNavigation()` without `Promise.all([...])`** — race condition.
- **`waitForLoadState('networkidle')`** — flaky/discouraged; assert on
  visible UI state instead.
- **`beforeAll(async ({ page }) => ...)`** — page fixture in `beforeAll` shares
  state across workers; use `beforeEach` or a fixture.
- **`page.evaluate()` with hardcoded JS or an inline arrow function** —
  bypasses auto-retry; use locator actions.
- **Hardcoded test data in a spec file** (`page.fill`/`.type` with a literal
  string) — use test data or config instead.
- **`await` inside `expect()` for locator-level getters**
  (`expect(await locator.textContent())`) — bypasses web-first auto-retry;
  use `await expect(locator).toHaveText()`/`toBeVisible()` etc. instead.
- **`@ts-ignore` / `@ts-expect-error`** with no justifying comment on the
  same line — add a reason or fix the underlying type error.
- **Untyped custom fixtures** — `base.extend()`/`test.extend()` without a
  generic `Fixtures` type parameter.
- **Playwright test framework imported without a `Page`/`Locator` type** in a
  page object file — verify this import is actually needed there.

## Medium

- **TypeScript `any` / `as any` / `Promise<any>`** — defeats type safety; use
  specific types.
- **TypeScript non-null assertion `!`** — handle the undefined/null case
  explicitly instead of asserting it away.
- **`page.reload()` without a follow-up assertion** — verify page state after.
- **Always-on `page.screenshot()`** — gate behind failure hooks.
- **`await` inside `expect()`** for async page-level getters
  (`expect(await page.title())`) — hoist the await:
  `const t = await page.title(); expect(t)...`.
- **`page: Page` passed as a parameter to a helper function** — consider a
  fixture or POM method instead.
- **High retry counts** (`retries: 3` or more) — may mask flakiness rather
  than addressing the root cause.
- **`test.describe.serial()`** — verify tests are genuinely order-dependent,
  not hiding coupling.

## Low (insights, non-blocking)

- Test missing a `@tag` annotation — harder to filter in CI.
- `test.setTimeout()` inside a test (any value other than `0`, which is
  Critical above) — prefer a global setting in the config.
- `page.fill(selector, value)` — the older API; prefer `locator.fill()`.
- Empty or missing `describe()` label.
- `getByRole`/`getByTestId`/`getByText`/`getByLabel`/`getByPlaceholder`/
  `getByAltText`/`getByTitle` — consider `page.locator()` with a CSS selector
  per this repo's locator strategy.
- `toHaveScreenshot()` called with no options — consider `mask`/
  `maxDiffPixelRatio` for dynamic regions.

## Conventions

- Test files must end in `.spec.ts` so the runner discovers them.
- Page objects under `src/ui/pages/`; test data in `testdata/` or config, not inline.
