#!/usr/bin/env python3
"""
playwright-ts -- deterministic patterns (Layer 1).

Applied ON TOP of qa-review-core when the repo uses @playwright/test WITH
TypeScript. Runtime rules are identical to playwright-js (same Playwright
API, same async pitfalls) so this module re-exports that skill's patterns and
adds only the TypeScript-specific ones. No LLM involved.
"""

import importlib.util
from pathlib import Path

# Reuse playwright-js's patterns rather than duplicating them -- the two
# skills share the exact same runtime (Playwright) API surface. Entries that
# need a different regex/severity for this overlay are filtered back out of
# the copied list below and replaced with a TS-tuned version.
_js_review_path = Path(__file__).resolve().parents[2] / "playwright-js" / "scripts" / "review.py"
_spec = importlib.util.spec_from_file_location("_playwright_js_review", _js_review_path)
_playwright_js = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_playwright_js)

# ---------------------------------------------------------------------------
# CRITICAL
# ---------------------------------------------------------------------------
# Drop playwright-js's "missing await" entry -- replaced below with a version
# that also covers focus()/dragTo(), which SKILL.md's action list includes.
_critical_from_js = [
    (p, r) for (p, r) in _playwright_js.CRITICAL_PATTERNS if "missing await" not in r.lower()
]

CRITICAL_PATTERNS = _critical_from_js + [
    # Unawaited Playwright actions -- same as playwright-js but with the full
    # action list from SKILL.md (adds focus, dragTo).
    (r"(?!.*\bawait\b).*\.page\.(goto|click|fill|check|uncheck|selectOption|hover|dblclick|tap|press|type|setInputFiles|dragAndDrop|dragTo|focus)\s*\(",
     "Possible missing await on Playwright page action -- unawaited actions silently no-op"),

    # await on a locator *creation* with no chained action -- locators are lazy;
    # awaiting the creation itself (instead of the action on it) is a logic error.
    (r"await\s+(?:this\.)?page\.locator\s*\([^)]*\)\s*;",
     "await used on locator creation with no chained action -- locators are lazy, awaiting the creation itself is likely a logic error"),

    # Conditional assertions that can silently no-op, e.g.
    # if (await locator.isVisible()) { await expect(...) } -- the branch may
    # never run and the test passes vacuously.
    (r"if\s*\(\s*await\s+[\w.]+\.(isVisible|isEnabled|isChecked|isDisabled|isEditable|isHidden)\s*\(\s*\)\s*\)\s*\{",
     "Conditional assertion guarded by isVisible/isEnabled/etc. -- the branch may never run, letting the test pass vacuously"),

    # test.setTimeout(0) disables timeouts globally to mask flakiness.
    (r"test\.setTimeout\s*\(\s*0\s*\)",
     "test.setTimeout(0) disables the timeout globally -- masks flakiness instead of fixing the root cause"),
]

# ---------------------------------------------------------------------------
# HIGH
# ---------------------------------------------------------------------------
# Drop playwright-js's test.only/describe.only entry from LOW (see below) --
# SKILL.md classifies it as High for this overlay ("silently skips the rest
# of the suite in CI").
HIGH_PATTERNS = list(_playwright_js.HIGH_PATTERNS) + [
    (r"(test|it|describe)\.only\s*\(",
     "test.only/describe.only committed -- silently skips the rest of the suite in CI; remove before merging"),

    # networkidle waits are flaky and discouraged.
    (r"waitForLoadState\s*\(\s*['\"]networkidle['\"]",
     "waitForLoadState('networkidle') is flaky/discouraged -- assert on visible UI state instead"),

    # More deprecated APIs beyond $()/$$()/waitForSelector (already in playwright-js).
    (r"\.\$eval\s*\(", "Deprecated Playwright API $eval() detected -- use locator methods instead"),
    (r"\.\$\$eval\s*\(", "Deprecated Playwright API $$eval() detected -- use locator methods instead"),

    # .first() on a possibly-ambiguous set -- same fragility concern as .nth(0).
    (r"\.first\s*\(\s*\)",
     "Locator .first() used -- verify the set is genuinely ordered/unique, or prefer a more specific selector (getByRole/getByTestId)"),

    # Assertions without web-first auto-retry at the locator level (page-level
    # form is covered by qa-review-core's "await inside expect()" pattern).
    (r"expect\s*\(\s*await\s+[\w.]+\.(textContent|innerText|inputValue|isVisible|isChecked|isEnabled|getAttribute)\s*\(",
     "await inside expect() bypasses web-first auto-retry -- use await expect(locator).toHaveText()/toBeVisible() etc. instead"),

    # @ts-ignore / @ts-expect-error with no justification on the same line.
    (r"//\s*@ts-(?:ignore|expect-error)\s*$",
     "@ts-ignore/@ts-expect-error without a justifying comment -- add a reason or fix the underlying type error"),

    # Untyped custom fixtures -- base.extend()/test.extend() without a generic
    # Fixtures type (commonly `import { test as base } ...; export const test =
    # base.extend<Fixtures>({...})`, so match any receiver, not just `test.`).
    (r"\b\w+\.extend(?!\s*<)\s*\(",
     "*.extend() without a generic Fixtures type -- declare base.extend<Fixtures>() so consumers get type safety"),
]

# ---------------------------------------------------------------------------
# MEDIUM
# ---------------------------------------------------------------------------
MEDIUM_PATTERNS = list(_playwright_js.MEDIUM_PATTERNS) + [
    # TypeScript-only: defeats type safety.
    (r":\s*any\b", "TypeScript 'any' type detected -- use specific types to maintain type safety"),
    (r"as\s+any\b", "TypeScript 'as any' cast detected -- use proper typing instead"),
    (r"Promise<any>", "Promise<any> return type -- use a typed Promise<T> instead of Promise<any>"),

    # TypeScript-only: non-null assertion operator defeats null-safety.
    (r"[A-Za-z_$][\w$]*!\.", "TypeScript non-null assertion '!' used -- handle the undefined/null case explicitly instead of asserting it away"),

    # TypeScript-only: page: Page passed as a parameter to a helper.
    (r"(function|const)\s+\w+\s*\([^)]*\bpage\s*:\s*Page\b", "page: Page passed as parameter to helper -- consider using a fixture or POM method instead"),

    # High retry counts can mask flakiness rather than fixing the root cause.
    (r"retries\s*:\s*([3-9]|\d{2,})\b", "High retries count configured -- may mask flakiness rather than addressing the root cause"),

    # test.describe.serial can hide inter-test coupling.
    (r"test\.describe\.serial\s*\(", "test.describe.serial() used -- verify tests are genuinely order-dependent, not hiding coupling"),
]

# ---------------------------------------------------------------------------
# LOW
# ---------------------------------------------------------------------------
# Drop playwright-js's test.only/describe.only insight -- elevated to HIGH above.
LOW_PATTERNS = [
    (p, r) for (p, r) in _playwright_js.LOW_PATTERNS if "test.only" not in r.lower()
] + [
    # Snapshot/visual comparisons without an explicit masking/threshold strategy.
    (r"toHaveScreenshot\s*\(\s*\)",
     "Insight: toHaveScreenshot() called with no options -- consider mask/maxDiffPixelRatio for dynamic regions"),
]
