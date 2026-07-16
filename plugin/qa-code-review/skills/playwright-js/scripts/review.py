#!/usr/bin/env python3
"""
playwright-js -- deterministic patterns (Layer 1).

Applied ON TOP of qa-review-core when the repo uses @playwright/test without
TypeScript. Runtime behaviour matches Playwright-TS; the difference is no
compiler safety net, so async and locator mistakes are easier to ship.
No LLM involved -- plain regexes, reproducible and authoritative.

Each pattern is a Check(id, rule, suggestion, regex, scope, flags) -- see
qa-review-core/scripts/review.py's module docstring for the exact scope/flags
contract, which is shared across every skill.
"""

from collections import namedtuple

Check = namedtuple("Check", ["id", "rule", "suggestion", "regex", "scope", "flags"])

CRITICAL_PATTERNS = [
    # Unawaited Playwright actions -- silently no-op in JS with no compiler to catch it.
    Check("PWJS-AWAIT", "Possible missing await on Playwright page action -- unawaited actions silently no-op",
          "Add await -- unawaited actions silently no-op and race.",
          r"\bpage\.(goto|click|fill|check|uncheck|selectOption|hover|dblclick|tap|press|type|setInputFiles|dragAndDrop)\s*\(",
          "any", frozenset({"no_await"})),

    # Missing await on wait-for-event promises. A dropped (unassigned,
    # unawaited) wait promise races ahead of the event; an assignment or
    # Promise.all with the triggering action is the idiomatic deferred pattern
    # and must NOT be flagged (flags: defer_ok).
    Check("PWJS-AWAIT-EVENT", "Possible missing await on wait-for-event -- unawaited waits race ahead of the event",
          "Await it, assign it for a later await, or use Promise.all([...]) with the action that triggers it.",
          r"\bpage\.(waitForResponse|waitForRequest|waitForEvent|waitForURL|waitForFunction)\s*\(",
          "any", frozenset({"no_await", "defer_ok"})),

    # Nested test() inside another test() body -- causes a Playwright runtime error.
    # Context-aware (must distinguish from valid test() inside test.describe());
    # handled as a shared, engine-level check in deterministic_review.py
    # (id "PW-NESTED-TEST"), not via a simple regex here.
]

HIGH_PATTERNS = [
    # Deprecated Playwright APIs.
    Check("PWJS-DOLLAR-API", "Deprecated Playwright API $() detected -- use page.locator() instead",
          "Use page.locator().",
          r"\.\$\s*\(", "any", frozenset()),
    Check("PWJS-DOLLAR-API", "Deprecated Playwright API $$() detected -- use page.locator() instead",
          "Use page.locator().",
          r"\.\$\$\s*\(", "any", frozenset()),
    Check("PWJS-WAIT-SELECTOR", "page.waitForSelector() detected -- use expect(locator).toBeVisible() for auto-retry",
          "Use expect(locator).toBeVisible() for auto-retry.",
          r"page\.waitForSelector\s*\(", "any", frozenset()),
    Check("PWJS-DOLLAR-EVAL", "Deprecated page.$eval()/$$eval() detected -- use locator methods instead",
          "Use locator.evaluate()/evaluateAll(), or (preferred) locator actions with auto-retry.",
          r"\.\$\$?eval\s*\(", "any", frozenset()),

    # page.waitForNavigation() without Promise.all -- race condition risk.
    Check("PWJS-WAIT-NAV", "page.waitForNavigation() without Promise.all -- wrap with Promise.all([page.waitForNavigation(), ...]) to avoid race condition",
          "Wrap with Promise.all([page.waitForNavigation(), <action>]).",
          r"(?<!Promise\.all\(\[).*page\.waitForNavigation\s*\(", "any", frozenset()),

    # beforeAll used for page navigation/login -- shared state across workers is unsafe.
    Check("PWJS-BEFOREALL-PAGE", "beforeAll() used with page fixture -- use beforeEach() or fixtures to avoid shared state across workers",
          "Use beforeEach() or a fixture -- beforeAll shares state across workers.",
          r"beforeAll\s*\(\s*async\s*\([^)]*page[^)]*\)", "any", frozenset()),

    # page.evaluate() with hardcoded JS -- bypasses Playwright auto-retry, fragile.
    Check("PWJS-EVALUATE-HARDCODED", "page.evaluate() with hardcoded JS string -- use locator actions with auto-retry instead",
          "Use locator actions with auto-retry.",
          r"page\.evaluate\s*\(\s*['\"`]", "any", frozenset()),
    Check("PWJS-EVALUATE-HARDCODED", "page.evaluate() with inline arrow function -- use Playwright locator actions for auto-retry support",
          "Use locator actions with auto-retry.",
          r"page\.evaluate\s*\(\s*\(\s*\)\s*=>", "any", frozenset()),

    # waitForLoadState('networkidle') is flaky and discouraged by Playwright.
    Check("PWJS-NETWORKIDLE", "waitForLoadState('networkidle') is flaky/discouraged -- assert on visible UI state instead",
          "Wait for a concrete condition (a locator/response) instead.",
          r"waitForLoadState\s*\(\s*['\"]networkidle['\"]", "any", frozenset()),

    # { force: true } bypasses actionability checks and masks real UI defects.
    Check("PWJS-FORCE-TRUE", "{ force: true } bypasses actionability checks -- fix the root cause or justify with a ticket",
          "Remove force:true and fix the root cause, or justify it in a comment with a ticket.",
          r"\.(click|fill|check|uncheck|selectOption|tap|dblclick|setChecked|hover)\s*\([^)]*force\s*:\s*true",
          "any", frozenset()),

    # Non-retrying assertion on a LOCATOR method (not a page-level getter --
    # that's PWJS-EXPECT-AWAIT-GETTER, Medium, below). Excludes "page." via
    # negative lookahead so the two checks never double-fire on one line.
    Check("PWJS-NONRETRY-LOCATOR", "Non-retrying assertion on a dynamic locator value -- bypasses web-first auto-retry",
          "Use the auto-retrying web-first form, e.g. expect(locator).toHaveText(x) instead of expect(await locator.textContent()).toBe(x).",
          r"expect\s*\(\s*await\s+(?!page\.)[\w.]+\.(textContent|innerText|inputValue|isVisible|isChecked|isEnabled|getAttribute)\s*\(",
          "any", frozenset()),

    # Hardcoded test data in spec files.
    Check("PWJS-HARDCODE-DATA", "Possible hardcoded test data in spec -- use testdata or config",
          "Move test data to fixtures/config.",
          r"(page\.fill|\.type)\s*\([^,]+,\s*['\"](?!.*\$|.*\{).{5,}['\"]", "spec", frozenset()),

    # Playwright test framework imported inside a page object file -- only
    # meaningful in a page object; a type-only import (Page/Locator) is fine.
    Check("PWJS-PW-IMPORT", "Playwright test framework imported without Page type -- verify this is needed",
          "Page objects should not import test/expect; import only the Page/Locator types.",
          r"import\s+\{[^}]*\}\s+from\s+['\"]@playwright/test['\"]",
          "page_object", frozenset({"skip_if_pagetype"})),
]

MEDIUM_PATTERNS = [
    # page.reload() without a follow-up assertion.
    Check("PWJS-RELOAD-NOASSERT", "page.reload() without follow-up assertion -- add expect() to verify page state after reload",
          "Add an expect() to verify page state after reload.",
          r"await\s+page\.reload\s*\(\s*\)", "any", frozenset()),

    # page.screenshot() left unconditionally -- slows down test runs if always-on.
    Check("PWJS-SCREENSHOT-ALWAYS", "page.screenshot() detected -- ensure this is conditional or inside onTestFailed hook, not always-on",
          "Gate behind a failure hook (onTestFailed), not on every run.",
          r"page\.screenshot\s*\(", "any", frozenset()),

    # page passed as parameter between helper functions -- signals missing fixture/POM abstraction.
    Check("PWJS-PAGE-PARAM", "page passed as parameter to helper -- consider using a fixture or POM method instead",
          "Consider using a fixture or POM method instead.",
          r"(function|const)\s+\w+\s*\([^)]*\bpage\s*,", "any", frozenset()),

    # Missing await before expect when using an async PAGE-LEVEL getter (not a
    # locator method -- that's PWJS-NONRETRY-LOCATOR, High, above).
    Check("PWJS-EXPECT-AWAIT-GETTER", "await inside expect() -- move await outside: const val = await ...; expect(val)",
          "Hoist the await: const val = await page.title(); expect(val)...",
          r"expect\s*\(\s*await\s+page\.(title|url|content|innerText|textContent|inputValue)\s*\(",
          "any", frozenset()),
]

LOW_PATTERNS = [
    # test.only / describe.only should never be committed.
    Check("PWJS-TEST-ONLY", "test.only/describe.only committed -- will block other tests from running",
          "Remove .only -- it blocks the rest of the suite.",
          r"(test|it|describe)\.only\s*\(", "any", frozenset()),

    # test.setTimeout() inside a test -- override in playwright.config.js instead.
    Check("PWJS-SET-TIMEOUT", "Insight: test.setTimeout() inside test -- set timeout globally in playwright.config.js instead",
          "Set the timeout globally in playwright.config.js instead.",
          r"test\.setTimeout\s*\(", "any", frozenset()),

    # page.fill() old API -- prefer locator.fill().
    Check("PWJS-FILL-OLD-API", "Insight: page.fill(selector, value) is the older API -- prefer locator.fill() for better reliability",
          "Prefer locator.fill() for better reliability.",
          r"page\.fill\s*\(", "any", frozenset()),

    # Unnamed describe block.
    Check("PWJS-DESCRIBE-EMPTY", "Insight: Empty describe() label -- give suites a meaningful name for report readability",
          "Give the suite a meaningful name.",
          r"describe\s*\(\s*['\"]['\"]", "any", frozenset()),
    Check("PWJS-DESCRIBE-EMPTY", "Insight: describe() called without a label -- add a meaningful suite name",
          "Add a meaningful suite name.",
          r"describe\s*\(\s*,", "any", frozenset()),

    # Missing @tag annotation on tests -- hard to filter in CI.
    Check("PWJS-NO-TAG", "Insight: Test has no @tag annotation -- consider adding tags (e.g., '@smoke', '@regression') for CI filtering",
          "Add tags (e.g. @smoke, @regression) for CI filtering.",
          r"test\s*\(\s*['\"](?!.*@)", "any", frozenset()),

    # Playwright built-in locator methods -- informational only, repo prefers page.locator() with CSS.
    Check("PWJS-GETBYROLE", "Insight: getByRole() detected -- consider page.locator() with CSS selector per repo locator strategy",
          "Consider page.locator() with a CSS selector per this repo's locator strategy.",
          r"\.getByRole\s*\(", "any", frozenset()),
    Check("PWJS-GETBYTESTID", "Insight: getByTestId() detected -- consider page.locator('[data-testid=\"...\"]') directly",
          "Consider page.locator('[data-testid=\"...\"]') directly.",
          r"\.getByTestId\s*\(", "any", frozenset()),
    Check("PWJS-GETBYTEXT", "Insight: getByText() detected -- consider page.locator() with CSS or XPath",
          "Consider page.locator() with CSS or XPath.",
          r"\.getByText\s*\(", "any", frozenset()),
    Check("PWJS-GETBYLABEL", "Insight: getByLabel() detected -- consider page.locator() with CSS selector",
          "Consider page.locator() with a CSS selector.",
          r"\.getByLabel\s*\(", "any", frozenset()),
    Check("PWJS-GETBYPLACEHOLDER", "Insight: getByPlaceholder() detected -- consider page.locator('[placeholder=\"...\"]')",
          "Consider page.locator('[placeholder=\"...\"]').",
          r"\.getByPlaceholder\s*\(", "any", frozenset()),
    Check("PWJS-GETBYALTTEXT", "Insight: getByAltText() detected -- consider page.locator() with CSS selector",
          "Consider page.locator() with a CSS selector.",
          r"\.getByAltText\s*\(", "any", frozenset()),
    Check("PWJS-GETBYTITLE", "Insight: getByTitle() detected -- consider page.locator() with CSS selector",
          "Consider page.locator() with a CSS selector.",
          r"\.getByTitle\s*\(", "any", frozenset()),
]
