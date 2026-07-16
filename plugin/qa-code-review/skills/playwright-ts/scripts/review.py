#!/usr/bin/env python3
"""
playwright-ts -- deterministic patterns (Layer 1).

Applied ON TOP of qa-review-core when the repo uses @playwright/test WITH
TypeScript. Runtime rules are identical to playwright-js (same Playwright
API, same async pitfalls) so this module re-exports that skill's Check
patterns and adds only the TypeScript-specific ones + a few extra checks
that happen to have been authored here first. No LLM involved.

Filtering the inherited list is done by Check.id (stable, not a text
substring match on the rule string) -- much more robust than the old
"rule_name.lower()" string sniffing.
"""

import importlib.util
from collections import namedtuple
from pathlib import Path

Check = namedtuple("Check", ["id", "rule", "suggestion", "regex", "scope", "flags"])

# Reuse playwright-js's Check instances rather than duplicating them -- the
# two skills share the exact same runtime (Playwright) API surface. Entries
# that need a different regex/severity for this overlay are filtered back out
# of the copied list below and replaced with a TS-tuned version.
_js_review_path = Path(__file__).resolve().parents[2] / "playwright-js" / "scripts" / "review.py"
_spec = importlib.util.spec_from_file_location("_playwright_js_review", _js_review_path)
_playwright_js = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_playwright_js)


def _drop(checks, *ids):
    """Return checks with the given ids removed (by stable id, not rule text)."""
    return [c for c in checks if c.id not in ids]


# ---------------------------------------------------------------------------
# CRITICAL
# ---------------------------------------------------------------------------
# Drop playwright-js's "missing await" entry -- replaced below with a version
# that also covers focus()/dragTo(), which SKILL.md's action list includes.
_critical_from_js = _drop(_playwright_js.CRITICAL_PATTERNS, "PWJS-AWAIT")

CRITICAL_PATTERNS = _critical_from_js + [
    # Unawaited Playwright actions -- same as playwright-js but with the full
    # action list from SKILL.md (adds focus, dragTo).
    Check("PWTS-AWAIT", "Possible missing await on Playwright page action -- unawaited actions silently no-op",
          "Add await -- unawaited actions silently no-op and race.",
          r"\bpage\.(goto|click|fill|check|uncheck|selectOption|hover|dblclick|tap|press|type|setInputFiles|dragAndDrop|dragTo|focus)\s*\(",
          "any", frozenset({"no_await"})),

    # await on a locator *creation* with no chained action -- locators are lazy;
    # awaiting the creation itself (instead of the action on it) is a logic error.
    Check("PWTS-AWAIT-LOCATOR-CREATION", "await used on locator creation with no chained action -- locators are lazy, awaiting the creation itself is likely a logic error",
          "Await the action on the locator, not the locator's creation.",
          r"await\s+(?:this\.)?page\.locator\s*\([^)]*\)\s*;",
          "any", frozenset()),

    # Conditional assertions that can silently no-op, e.g.
    # if (await locator.isVisible()) { await expect(...) } -- the branch may
    # never run and the test passes vacuously.
    Check("PWTS-VACUOUS-CONDITIONAL", "Conditional assertion guarded by isVisible/isEnabled/etc. -- the branch may never run, letting the test pass vacuously",
          "Assert unconditionally, or fail explicitly in the else branch.",
          r"if\s*\(\s*await\s+[\w.]+\.(isVisible|isEnabled|isChecked|isDisabled|isEditable|isHidden)\s*\(\s*\)\s*\)\s*\{",
          "any", frozenset()),

    # test.setTimeout(0) disables timeouts globally to mask flakiness.
    Check("PWTS-SETTIMEOUT-ZERO", "test.setTimeout(0) disables the timeout globally -- masks flakiness instead of fixing the root cause",
          "Fix the root cause of the slowness instead of disabling the timeout.",
          r"test\.setTimeout\s*\(\s*0\s*\)",
          "any", frozenset()),
]

# ---------------------------------------------------------------------------
# HIGH
# ---------------------------------------------------------------------------
# Drop playwright-js's test.only/describe.only entry from LOW (see below) --
# SKILL.md classifies it as High for this overlay ("silently skips the rest
# of the suite in CI"). PWJS-NETWORKIDLE, PWJS-DOLLAR-EVAL, and
# PWJS-NONRETRY-LOCATOR are inherited as-is (no TS-specific variant needed).
HIGH_PATTERNS = list(_playwright_js.HIGH_PATTERNS) + [
    Check("PWTS-TEST-ONLY", "test.only/describe.only committed -- silently skips the rest of the suite in CI; remove before merging",
          "Remove .only before merging -- it silently skips the rest of the suite.",
          r"(test|it|describe)\.only\s*\(", "any", frozenset()),

    # .first() on a possibly-ambiguous set -- same fragility concern as .nth(0).
    Check("PWTS-FIRST-FRAGILE", "Locator .first() used -- verify the set is genuinely ordered/unique, or prefer a more specific selector",
          "Verify the set is genuinely ordered/unique, or prefer a more specific selector (getByRole/getByTestId).",
          r"\.first\s*\(\s*\)", "any", frozenset()),

    # @ts-ignore / @ts-expect-error with no justification on the same line.
    Check("PWTS-TS-IGNORE", "@ts-ignore/@ts-expect-error without a justifying comment -- add a reason or fix the underlying type error",
          "Add a reason or fix the underlying type error.",
          r"//\s*@ts-(?:ignore|expect-error)\s*$", "any", frozenset()),

    # Untyped custom fixtures -- base.extend()/test.extend() without a generic
    # Fixtures type (commonly `import { test as base } ...; export const test =
    # base.extend<Fixtures>({...})`, so match any receiver, not just `test.`).
    Check("PWTS-UNTYPED-EXTEND", "*.extend() without a generic Fixtures type -- declare base.extend<Fixtures>() so consumers get type safety",
          "Declare base.extend<Fixtures>() so consumers get type safety.",
          r"\b\w+\.extend(?!\s*<)\s*\(", "any", frozenset()),
]

# ---------------------------------------------------------------------------
# MEDIUM
# ---------------------------------------------------------------------------
MEDIUM_PATTERNS = list(_playwright_js.MEDIUM_PATTERNS) + [
    # TypeScript-only: defeats type safety.
    Check("PWTS-ANY-TYPE", "TypeScript 'any' type detected -- use specific types to maintain type safety",
          "Use specific types instead of any.",
          r":\s*any\b", "any", frozenset()),
    Check("PWTS-ANY-TYPE", "TypeScript 'as any' cast detected -- use proper typing instead",
          "Use proper typing instead of an 'as any' cast.",
          r"as\s+any\b", "any", frozenset()),
    Check("PWTS-ANY-TYPE", "Promise<any> return type -- use a typed Promise<T> instead of Promise<any>",
          "Use a typed Promise<T> instead of Promise<any>.",
          r"Promise<any>", "any", frozenset()),

    # TypeScript-only: non-null assertion operator defeats null-safety.
    Check("PWTS-NONNULL-ASSERT", "TypeScript non-null assertion '!' used -- handle the undefined/null case explicitly instead of asserting it away",
          "Handle the undefined/null case explicitly instead of asserting it away.",
          r"[A-Za-z_$][\w$]*!\.", "any", frozenset()),

    # TypeScript-only: page: Page passed as a parameter to a helper.
    Check("PWTS-PAGE-PARAM-TYPED", "page: Page passed as parameter to helper -- consider using a fixture or POM method instead",
          "Consider using a fixture or POM method instead.",
          r"(function|const)\s+\w+\s*\([^)]*\bpage\s*:\s*Page\b", "any", frozenset()),

    # High retry counts can mask flakiness rather than fixing the root cause.
    Check("PWTS-HIGH-RETRIES", "High retries count configured -- may mask flakiness rather than addressing the root cause",
          "Investigate and fix the root cause of the flakiness instead of retrying.",
          r"retries\s*:\s*([3-9]|\d{2,})\b", "any", frozenset()),

    # test.describe.serial can hide inter-test coupling.
    Check("PWTS-DESCRIBE-SERIAL", "test.describe.serial() used -- verify tests are genuinely order-dependent, not hiding coupling",
          "Verify tests are genuinely order-dependent, not hiding coupling.",
          r"test\.describe\.serial\s*\(", "any", frozenset()),
]

# ---------------------------------------------------------------------------
# LOW
# ---------------------------------------------------------------------------
# Drop playwright-js's test.only/describe.only insight -- elevated to HIGH above.
LOW_PATTERNS = _drop(_playwright_js.LOW_PATTERNS, "PWJS-TEST-ONLY") + [
    # Snapshot/visual comparisons without an explicit masking/threshold strategy.
    Check("PWTS-SCREENSHOT-NO-OPTIONS", "Insight: toHaveScreenshot() called with no options -- consider mask/maxDiffPixelRatio for dynamic regions",
          "Consider mask/maxDiffPixelRatio options for dynamic regions.",
          r"toHaveScreenshot\s*\(\s*\)", "any", frozenset()),
]
