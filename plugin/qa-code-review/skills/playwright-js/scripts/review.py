#!/usr/bin/env python3
"""
playwright-js -- deterministic patterns (Layer 1).

Applied ON TOP of qa-review-core when the repo uses @playwright/test without
TypeScript. Runtime behaviour matches Playwright-TS; the difference is no
compiler safety net, so async and locator mistakes are easier to ship.
No LLM involved -- plain regexes, reproducible and authoritative.
"""

CRITICAL_PATTERNS = [
    # Unawaited Playwright actions -- silently no-op in JS with no compiler to catch it.
    # Line-level check: only flags if 'await' does NOT appear anywhere on the same line.
    (r"(?!.*\bawait\b).*\.page\.(goto|click|fill|check|uncheck|selectOption|hover|dblclick|tap|press|type|setInputFiles|dragAndDrop)\s*\(",
     "Possible missing await on Playwright page action -- unawaited actions silently no-op"),

    # Nested test() inside another test() body -- causes a Playwright runtime error.
    # Context-aware (must distinguish from valid test() inside test.describe());
    # handled in deterministic_review.py's analyze_file_content, not via a simple regex here.
]

HIGH_PATTERNS = [
    # Deprecated Playwright APIs.
    (r"\.\$\s*\(", "Deprecated Playwright API $() detected -- use page.locator() instead"),
    (r"\.\$\$\s*\(", "Deprecated Playwright API $$() detected -- use page.locator() instead"),
    (r"page\.waitForSelector\s*\(", "page.waitForSelector() detected -- use expect(locator).toBeVisible() for auto-retry"),

    # page.waitForNavigation() without Promise.all -- race condition risk.
    (r"(?<!Promise\.all\(\[).*page\.waitForNavigation\s*\(",
     "page.waitForNavigation() without Promise.all -- wrap with Promise.all([page.waitForNavigation(), ...]) to avoid race condition"),

    # beforeAll used for page navigation/login -- shared state across workers is unsafe.
    (r"beforeAll\s*\(\s*async\s*\([^)]*page[^)]*\)",
     "beforeAll() used with page fixture -- use beforeEach() or fixtures to avoid shared state across workers"),

    # page.evaluate() with hardcoded JS -- bypasses Playwright auto-retry, fragile.
    (r"page\.evaluate\s*\(\s*['\"`]", "page.evaluate() with hardcoded JS string -- use locator actions with auto-retry instead"),
    (r"page\.evaluate\s*\(\s*\(\s*\)\s*=>", "page.evaluate() with inline arrow function -- use Playwright locator actions for auto-retry support"),

    # Hardcoded test data in spec files.
    (r"(page\.fill|\.type)\s*\([^,]+,\s*['\"](?!.*\$|.*\{).{5,}['\"]", "Possible hardcoded test data in spec -- use testdata or config"),
]

MEDIUM_PATTERNS = [
    # page.reload() without a follow-up assertion.
    (r"await\s+page\.reload\s*\(\s*\)", "page.reload() without follow-up assertion -- add expect() to verify page state after reload"),

    # page.screenshot() left unconditionally -- slows down test runs if always-on.
    (r"page\.screenshot\s*\(", "page.screenshot() detected -- ensure this is conditional or inside onTestFailed hook, not always-on"),

    # page passed as parameter between helper functions -- signals missing fixture/POM abstraction.
    (r"(function|const)\s+\w+\s*\([^)]*\bpage\s*,", "page passed as parameter to helper -- consider using a fixture or POM method instead"),

    # Missing await before expect when using async values.
    (r"expect\s*\(\s*await\s+page\.(title|url|content|innerText|textContent|inputValue)\s*\(",
     "await inside expect() -- move await outside: const val = await ...; expect(val)"),
]

LOW_PATTERNS = [
    # test.only / describe.only should never be committed.
    (r"(test|it|describe)\.only\s*\(", "test.only/describe.only committed -- will block other tests from running"),

    # test.setTimeout() inside a test -- override in playwright.config.js instead.
    (r"test\.setTimeout\s*\(", "Insight: test.setTimeout() inside test -- set timeout globally in playwright.config.js instead"),

    # page.fill() old API -- prefer locator.fill().
    (r"page\.fill\s*\(", "Insight: page.fill(selector, value) is the older API -- prefer locator.fill() for better reliability"),

    # Unnamed describe block.
    (r"describe\s*\(\s*['\"]['\"]", "Insight: Empty describe() label -- give suites a meaningful name for report readability"),
    (r"describe\s*\(\s*,", "Insight: describe() called without a label -- add a meaningful suite name"),

    # Missing @tag annotation on tests -- hard to filter in CI.
    (r"test\s*\(\s*['\"](?!.*@)", "Insight: Test has no @tag annotation -- consider adding tags (e.g., '@smoke', '@regression') for CI filtering"),

    # Playwright built-in locator methods -- informational only, repo prefers page.locator() with CSS.
    (r"\.getByRole\s*\(", "Insight: getByRole() detected -- consider page.locator() with CSS selector per repo locator strategy"),
    (r"\.getByTestId\s*\(", "Insight: getByTestId() detected -- consider page.locator('[data-testid=\"...\"]') directly"),
    (r"\.getByText\s*\(", "Insight: getByText() detected -- consider page.locator() with CSS or XPath"),
    (r"\.getByLabel\s*\(", "Insight: getByLabel() detected -- consider page.locator() with CSS selector"),
    (r"\.getByPlaceholder\s*\(", "Insight: getByPlaceholder() detected -- consider page.locator('[placeholder=\"...\"]')"),
    (r"\.getByAltText\s*\(", "Insight: getByAltText() detected -- consider page.locator() with CSS selector"),
    (r"\.getByTitle\s*\(", "Insight: getByTitle() detected -- consider page.locator() with CSS selector"),
]

# Playwright test import inside a page object file -- only meaningful when
# deterministic_review.py knows the file is a page object; kept here as a HIGH pattern with
# a rule-name marker deterministic_review.py's context-aware _check_line recognizes.
HIGH_PATTERNS.append(
    (r"import\s+\{[^}]*\}\s+from\s+['\"]@playwright/test['\"]",
     "Playwright test framework imported without Page type -- verify this is needed")
)
