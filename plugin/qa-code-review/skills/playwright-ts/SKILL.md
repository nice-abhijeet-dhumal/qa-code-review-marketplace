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
| `scripts/review.py` | Deterministic patterns for the rules below. Imports `playwright-js/scripts/review.py`'s `Check` instances (identical runtime API) and filters/extends them **by stable `id`** (not rule-text substring matching) to override the ones that need a TS-tuned version, then adds the TypeScript-only patterns (`any`/`as any`, non-null assertion, typed helper params, ...). Merged with `qa-review-core/scripts/review.py` by `deterministic_review.py` when this overlay is selected (detected via `@playwright/test` + `tsconfig.json`/`playwright.config.ts`). Review findings come only from this script — never from an LLM. |

## Critical

- **Missing `await` on Playwright actions.** `page.goto/click/fill/check/
  selectOption/hover/press/type/setInputFiles/dragAndDrop/dragTo/focus` etc.
  return promises; without `await` they silently no-op and create race
  conditions. Overrides `playwright-js`'s `PWJS-AWAIT` with the fuller action
  list. (`PWTS-AWAIT`)
- **`await` on a locator *creation* with no chained action** (e.g.
  `await page.locator('#x');` with nothing after it) — locators are lazy;
  awaiting the creation itself instead of an action on it is a logic error. (`PWTS-AWAIT-LOCATOR-CREATION`)
- **Conditional assertion guarded by `isVisible`/`isEnabled`/etc.**
  (`if (await locator.isVisible()) { await expect(...) }`) — the branch may
  never run, letting the test pass vacuously. (`PWTS-VACUOUS-CONDITIONAL`)
- **`test.setTimeout(0)`** — disables the timeout globally, masking flakiness
  instead of fixing the root cause. (`PWTS-SETTIMEOUT-ZERO`)
- **Missing `await` on `waitForResponse`/`waitForRequest`/`waitForEvent`/
  `waitForURL`/`waitForFunction`** — a dropped wait promise races ahead of the
  event. (`PWJS-AWAIT-EVENT`, inherited)
- **`page.pause()`** committed — launches the Inspector and hangs CI forever. (`CORE-3`, from qa-review-core)
- **`waitForTimeout(>= 1000)`** in spec/test files — replace with
  `expect(locator).toBeVisible()` or `locator.waitFor()`. (In a page object,
  short stabilization waits are downgraded to Medium but still discouraged.) (`CORE-2`, from qa-review-core)
- **Nested `test()` inside another `test()` body** — Playwright throws at
  runtime. Note: `test()` inside `test.describe()` is valid and must NOT flag.
  Shared, engine-level check (`PW-NESTED-TEST`), not a regex in this file.

## High

- **`test.only` / `describe.only` committed** — silently skips the rest of
  the suite in CI; remove before merging. Overrides `playwright-js`'s Low
  `PWJS-TEST-ONLY` (removed from the inherited Low list). (`PWTS-TEST-ONLY`)
- **Locators in spec files** (`page.locator(...)` in a `.spec.ts`) — POM
  violation; move to a page object and expose a method. (`CORE-9`, from qa-review-core)
- **Value assertions in page objects** (`toBe`, `toEqual`, `toContain`,
  `toBeTruthy`, `toHaveCount`, ...) — move to the spec. `toBeVisible/
  toBeHidden/toBeEnabled` are allowed as auto-waits. (`CORE-9`, from qa-review-core)
- **Fragile locators:** `.nth(0)`, `:first-child`, absolute XPath
  (`//div/div/div[...]`), auto-generated IDs (`react-select-3-...`)
  (`CORE-11`, from qa-review-core); `.first()` — verify the set is genuinely
  ordered/unique (`PWTS-FIRST-FRAGILE`).
- **Deprecated APIs:** `$()`/`$$()`, `page.waitForSelector()`, `$eval()`/
  `$$eval()` — inherited from `playwright-js` (`PWJS-DOLLAR-API`,
  `PWJS-WAIT-SELECTOR`, `PWJS-DOLLAR-EVAL`).
- **`page.waitForNavigation()` without `Promise.all([...])`** — race condition. (`PWJS-WAIT-NAV`, inherited)
- **`waitForLoadState('networkidle')`** — flaky/discouraged; assert on
  visible UI state instead. (`PWJS-NETWORKIDLE`, inherited)
- **`beforeAll(async ({ page }) => ...)`** — page fixture in `beforeAll` shares
  state across workers; use `beforeEach` or a fixture. (`PWJS-BEFOREALL-PAGE`, inherited)
- **`page.evaluate()` with hardcoded JS or an inline arrow function** —
  bypasses auto-retry; use locator actions. (`PWJS-EVALUATE-HARDCODED`, inherited)
- **Hardcoded test data in a spec file** (`page.fill`/`.type` with a literal
  string) — use test data or config instead. (`PWJS-HARDCODE-DATA`, inherited)
- **`await` inside `expect()` for locator-level getters**
  (`expect(await locator.textContent())`) — bypasses web-first auto-retry;
  use `await expect(locator).toHaveText()`/`toBeVisible()` etc. instead. (`PWJS-NONRETRY-LOCATOR`, inherited)
- **`{ force: true }`** bypassing actionability checks. (`PWJS-FORCE-TRUE`, inherited)
- **`@ts-ignore` / `@ts-expect-error`** with no justifying comment on the
  same line — add a reason or fix the underlying type error. (`PWTS-TS-IGNORE`)
- **Untyped custom fixtures** — `base.extend()`/`test.extend()` without a
  generic `Fixtures` type parameter. (`PWTS-UNTYPED-EXTEND`)
- **Playwright test framework imported without a `Page`/`Locator` type** in a
  page object file — verify this import is actually needed there. (`PWJS-PW-IMPORT`, inherited)

## Medium

- **TypeScript `any` / `as any` / `Promise<any>`** — defeats type safety; use
  specific types. (`PWTS-ANY-TYPE`)
- **TypeScript non-null assertion `!`** — handle the undefined/null case
  explicitly instead of asserting it away. (`PWTS-NONNULL-ASSERT`)
- **`page.reload()` without a follow-up assertion** — verify page state after. (`PWJS-RELOAD-NOASSERT`, inherited)
- **Always-on `page.screenshot()`** — gate behind failure hooks. (`PWJS-SCREENSHOT-ALWAYS`, inherited)
- **`await` inside `expect()`** for async page-level getters
  (`expect(await page.title())`) — hoist the await:
  `const t = await page.title(); expect(t)...`. (`PWJS-EXPECT-AWAIT-GETTER`, inherited)
- **`page: Page` passed as a parameter to a helper function** — consider a
  fixture or POM method instead. (`PWTS-PAGE-PARAM-TYPED`; the untyped-param
  form `PWJS-PAGE-PARAM` is also inherited, for a helper param with no type
  annotation)
- **High retry counts** (`retries: 3` or more) — may mask flakiness rather
  than addressing the root cause. (`PWTS-HIGH-RETRIES`)
- **`test.describe.serial()`** — verify tests are genuinely order-dependent,
  not hiding coupling. (`PWTS-DESCRIBE-SERIAL`)

## Low (insights, non-blocking)

- Test missing a `@tag` annotation — harder to filter in CI. (`PWJS-NO-TAG`, inherited)
- `test.setTimeout()` inside a test (any value other than `0`, which is
  Critical above) — prefer a global setting in the config. (`PWJS-SET-TIMEOUT`, inherited)
- `page.fill(selector, value)` — the older API; prefer `locator.fill()`. (`PWJS-FILL-OLD-API`, inherited)
- Empty or missing `describe()` label. (`PWJS-DESCRIBE-EMPTY`, inherited)
- **Non-descriptive test titles** — shared, engine-level check
  (`PW-NONDESC-TITLE`), applies whenever the file is a spec, regardless of
  driver overlay.
- `getByRole`/`getByTestId`/`getByText`/`getByLabel`/`getByPlaceholder`/
  `getByAltText`/`getByTitle` — consider `page.locator()` with a CSS selector
  per this repo's locator strategy. (`PWJS-GETBYROLE`, `PWJS-GETBYTESTID`,
  `PWJS-GETBYTEXT`, `PWJS-GETBYLABEL`, `PWJS-GETBYPLACEHOLDER`,
  `PWJS-GETBYALTTEXT`, `PWJS-GETBYTITLE`, all inherited)
- `toHaveScreenshot()` called with no options — consider `mask`/
  `maxDiffPixelRatio` for dynamic regions. (`PWTS-SCREENSHOT-NO-OPTIONS`)

## Conventions

- Test files must end in `.spec.ts` so the runner discovers them.
- Page objects under `src/ui/pages/`; test data in `testdata/` or config, not inline.
