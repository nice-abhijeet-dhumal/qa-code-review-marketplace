#!/usr/bin/env python3
"""
qa-review-core -- deterministic patterns (Layer 1).

Framework-agnostic rules from SKILL.md's "Universal rules" section. Always
loaded by deterministic_review.py regardless of which driver overlay
(playwright-ts, playwright-js, selenium-java) is also active. No LLM involved
-- these are plain regexes, reproducible and authoritative.

Each pattern is a Check(id, rule, suggestion, regex, scope, flags):
  id       stable identifier (e.g. "CORE-6"), matches the numbered rule in
           SKILL.md so the two can be verified against each other mechanically.
  scope    "any" | "spec" | "page_object" | "not_page_object" | "not_pages_dir"
           -- see deterministic_review.py's _scope_allows() for exact semantics.
  flags    a set of behaviour modifiers -- see deterministic_review.py's
           _flag_excludes() for exact semantics. Empty set/frozenset if none.
Severity is implied by which list (CRITICAL_PATTERNS/HIGH_PATTERNS/...) a
Check lives in, except "downgrade_medium_in_page_object" (see waitForTimeout
below), which overrides to Medium inside a page object.
"""

from collections import namedtuple

Check = namedtuple("Check", ["id", "rule", "suggestion", "regex", "scope", "flags"])

CRITICAL_PATTERNS = [
    # Universal rule 4: no real assertions commented out.
    Check("CORE-4", "Commented-out assertion",
          "Re-enable the assertion or delete it; a disabled assertion is a silent gap.",
          r"//\s*(expect|assert|Assert\.|should)\s*[\.(]", "any", frozenset()),
    Check("CORE-4", "Commented-out assertion",
          "Re-enable the assertion or delete it; a disabled assertion is a silent gap.",
          r"#\s*(assert|self\.assert\w+)\s*[\.(]", "any", frozenset()),

    # Universal rule 5: no empty test bodies.
    Check("CORE-5", "Empty test body",
          "A test with no steps passes meaninglessly; implement it or remove it.",
          r"(it|test)\s*\([^)]*,\s*(\(\s*\)|async\s*\(\s*\))\s*=>\s*\{\s*\}\s*\)", "any", frozenset()),
    Check("CORE-5", "Empty @Test body",
          "A test with no steps passes meaninglessly; implement it or remove it.",
          r"@Test[^\n]*\n\s*(public|private)?\s*void\s+\w+\s*\([^)]*\)\s*\{\s*\}", "any", frozenset()),

    # Universal rule 2: no hardcoded/blind sleeps. >1s is Critical; downgraded
    # to Medium inside a page object (short stabilization waits). A single
    # pattern covers every 4+-digit value -- the old code had a second,
    # fully-overlapping "[1-9]\d{3,}" pattern that matched the exact same set
    # of values, producing a duplicate finding for the same line.
    Check("CORE-2", "Hardcoded waitForTimeout > 1s -- use waitFor/expect assertions",
          "Replace with expect(locator).toBeVisible() or locator.waitFor().",
          r"waitForTimeout\s*\(\s*\d{4,}", "any", frozenset({"downgrade_medium_in_page_object"})),
    Check("CORE-2", "Thread.sleep -- use explicit waits (WebDriverWait/ExpectedConditions)",
          "Use WebDriverWait + ExpectedConditions (explicit waits).",
          r"Thread\.sleep\s*\(", "any", frozenset()),
    Check("CORE-2", "time.sleep -- use an explicit wait instead of a blind sleep",
          "Use an explicit wait instead of a blind sleep.",
          r"time\.sleep\s*\(", "any", frozenset()),

    # Universal rule 1: no swallowed errors.
    Check("CORE-1", "Empty catch block swallowing errors",
          "Do not swallow errors; log via the logger or let the error propagate.",
          r"catch\s*\([^)]*\)\s*\{\s*\}", "any", frozenset()),
    Check("CORE-1", "Empty catch block swallowing errors",
          "Do not swallow errors; log via the logger or let the error propagate.",
          r"catch\s*\{\s*\}", "any", frozenset()),

    # Universal rule 3: no committed debugger/pause calls that hang CI.
    Check("CORE-3", "page.pause() committed -- remove before merging, it hangs CI",
          "Remove page.pause() before merging -- it hangs CI.",
          r"page\.pause\s*\(\s*\)", "any", frozenset()),
    Check("CORE-3", "debugger; statement committed -- remove before merging",
          "Remove the debugger statement -- it hangs CI.",
          r"(?<![.\w])debugger\s*;", "any", frozenset()),

    # Universal rule 6: hardcoded secrets ship a credential -- severity table
    # classifies this as Critical ("ships a secret"); keep in sync with that.
    Check("CORE-6", "Possible hardcoded credential -- use config or environment variables",
          "Read from config/env/secret store, not a literal. Encrypted vault values are allowed.",
          r"(password|secret|token|apikey)\s*[:=]\s*['\"][^'\"]{4,}['\"]", "any", frozenset({"skip_crypto"})),
]

HIGH_PATTERNS = [
    # Universal rule 8: skipped tests need a ticket reference.
    Check("CORE-8", "Skipped test without ticket reference (e.g., // LV-1234)",
          "Add a ticket reference (e.g. LV-1234) to the skip.",
          r"\b(?:xit|xdescribe|test\.skip|it\.skip|@Ignore|@Disabled)\b(?!.*(?:JIRA|CXDSK|TODO|BUG|ISSUE|LV-))",
          "any", frozenset()),

    # Universal rule 9: POM boundaries -- locators only in page objects.
    Check("CORE-9", "page.locator() used in spec file -- POM violation: move locator to page object and expose via a method",
          "Move the locator into a page object and expose it via a method.",
          r"page\.locator\s*\(", "spec", frozenset()),
    Check("CORE-9", "driver.findElement() used in a test class -- POM violation: move to a page object",
          "Move driver.findElement() into a page object and expose it via a method.",
          r"driver\.findElement\s*\(", "not_page_object", frozenset()),

    # Universal rule 9 (other direction): value assertions belong in specs, not
    # page objects. Matched as COMPLETE calls (trailing "\s*\(") so the bare
    # "toBe" alternative does NOT match the "toBe" prefix of the allowed
    # auto-waits toBeVisible/toBeHidden/toBeEnabled/etc. -- BUG FIX: the
    # previous version had no trailing "\(" and false-positived on every
    # allowed auto-wait call.
    Check("CORE-9", "Value assertion found in Page Object -- move to test file or return the value instead",
          "Move value assertions to the spec, or return the value instead.",
          r"expect\s*\((?:[^()]|\([^()]*\))*\)\s*\.\s*(?:not\.\s*)?(?:toBe|toEqual|toContain|toBeTruthy|toBeFalsy|toBeGreaterThan|toBeLessThan|toHaveLength|toMatch|toHaveCount)\s*\(",
          "page_object", frozenset()),
    Check("CORE-9", "Assertion found in Page Object -- move to the test class",
          "Move the assertion to the test class.",
          r"(Assert\.\w+|assertThat)\s*\(", "page_object", frozenset()),

    # Universal rule 11: fragile locators.
    Check("CORE-11", "Index-based locator nth(0) -- use a stable, unique selector instead",
          "Use a stable, unique selector.",
          r"\.nth\s*\(\s*0\s*\)", "any", frozenset()),
    Check("CORE-11", "Index-based selector :first-child -- use a stable, unique selector instead",
          "Use a stable, unique selector.",
          r":first-child(?![a-zA-Z-])", "any", frozenset()),
    Check("CORE-11", "Auto-generated dynamic ID in locator -- use a stable attribute instead",
          "Use a stable attribute.",
          r"react-select-\d+-", "any", frozenset()),
    Check("CORE-11", "Full absolute XPath detected -- use relative XPath or CSS selector",
          "Use a relative XPath or a CSS selector.",
          r"//\w+/\w+/\w+\[", "any", frozenset()),

    # Universal rule 7: no hardcoded environment URLs.
    Check("CORE-7", "Hardcoded URL -- import from config instead",
          "Import the base URL from config.",
          r"https?://[a-zA-Z0-9._-]+\.(livevox|com|net|io)/", "any", frozenset()),
]

MEDIUM_PATTERNS = [
    # Universal rule 10: no debug leftovers.
    Check("CORE-10", "console.log left in code -- remove before merging",
          "Remove it before merging.",
          r"console\.(log|warn|error|info|debug)\s*\(", "any", frozenset()),
    Check("CORE-10", "System.out.println left in code -- use the logging framework",
          "Use the logging framework (SLF4J/Log4j).",
          r"System\.out\.print", "any", frozenset()),
    Check("CORE-10", "print() left in code -- use the logging framework",
          "Use the logging framework.",
          r"^\s*print\s*\(", "any", frozenset()),

    # Complements CORE-2: short waits (< 1s) are still discouraged, just Medium
    # instead of Critical. A single pattern covers 1-3 digit values -- the old
    # code had a second, redundant \d{3} pattern that only ever matched a
    # subset already covered by \d{1,3}.
    Check("CORE-2", "waitForTimeout usage -- prefer expect() auto-waiting",
          "Prefer expect() auto-waiting over a fixed short wait.",
          r"waitForTimeout\s*\(\s*\d{1,3}\s*\)", "any", frozenset()),

    # Additional check (not in the numbered Universal rules list): config
    # import path convention.
    Check("CORE-CONFIG-PATH", "Config import not from src/config/stg4 or src/config/tst2",
          "Import config from src/config/stg4 or src/config/tst2.",
          r"from\s+['\"]\.\.\/\.\.\/config(?!\/stg4|\/tst2)", "any", frozenset()),

    # Additional check: page class location.
    Check("CORE-PAGE-CLASS-LOC", "Page class detected -- verify it is placed under the pages/page-objects folder",
          "Move this class under a pages/ or page-objects/ folder.",
          r"class\s+\w+Page\s+", "not_pages_dir", frozenset()),

    # Additional check: no emojis / non-standard characters in comments
    # (excludes box-drawing separators and em/en-dash, common intentional
    # decorators).
    Check("CORE-NONASCII-COMMENT", "Non-ASCII character in comment -- keep comments plain ASCII",
          "Keep comments plain ASCII.",
          r"//(?!.*[─-╿—–]).*[^\x00-\x7F]", "any", frozenset()),
]

LOW_PATTERNS = [
    # Universal rule 12: track TODO/FIXME/HACK with a ticket reference.
    Check("CORE-12", "TODO/FIXME/HACK comment -- track in Jira with a ticket reference",
          "Track it in Jira with a ticket reference.",
          r"TODO|FIXME|HACK|XXX", "any", frozenset()),
]
