#!/usr/bin/env python3
"""
qa-review-core -- deterministic patterns (Layer 1).

Framework-agnostic rules from SKILL.md's "Universal rules" section. Always
loaded by deterministic_review.py regardless of which driver overlay (playwright-ts,
playwright-js, selenium-java) is also active. No LLM involved -- these are
plain regexes, reproducible and authoritative.

Each pattern is (regex, rule_name). Severity is implied by which list it is
in; deterministic_review.py handles the few rules that need line context (is_page_object,
is_spec_file) by matching on a substring of rule_name -- see deterministic_review.py's
_check_line docstring for the exact contract a rule name must follow to opt
into that context-aware behaviour.
"""

CRITICAL_PATTERNS = [
    # Universal rule 4: no real assertions commented out.
    (r"//\s*(expect|assert|Assert\.|should)\s*[\.(]", "Commented-out assertion"),
    (r"#\s*(assert|self\.assert\w+)\s*[\.(]", "Commented-out assertion"),

    # Universal rule 5: no empty test bodies.
    (r"(it|test)\s*\([^)]*,\s*(\(\s*\)|async\s*\(\s*\))\s*=>\s*\{\s*\}\s*\)", "Empty test body"),
    (r"@Test[^\n]*\n\s*(public|private)?\s*void\s+\w+\s*\([^)]*\)\s*\{\s*\}", "Empty @Test body"),

    # Universal rule 2: no hardcoded/blind sleeps. >1s is Critical; deterministic_review.py
    # downgrades this to Medium inside page objects (short stabilization waits).
    (r"waitForTimeout\s*\(\s*\d{4,}", "Hardcoded waitForTimeout > 1s -- use waitFor/expect assertions"),
    (r"waitForTimeout\s*\(\s*[1-9]\d{3,}", "Hardcoded waitForTimeout > 1s -- use waitFor/expect assertions"),
    (r"Thread\.sleep\s*\(", "Thread.sleep -- use explicit waits (WebDriverWait/ExpectedConditions)"),
    (r"time\.sleep\s*\(", "time.sleep -- use an explicit wait instead of a blind sleep"),

    # Universal rule 1: no swallowed errors.
    (r"catch\s*\([^)]*\)\s*\{\s*\}", "Empty catch block swallowing errors"),
    (r"catch\s*\{\s*\}", "Empty catch block swallowing errors"),

    # Universal rule 3: no committed debugger/pause calls that hang CI.
    (r"page\.pause\s*\(\s*\)", "page.pause() committed -- remove before merging, it hangs CI"),
    (r"(?<![.\w])debugger\s*;", "debugger; statement committed -- remove before merging"),

    # Universal rule 6: hardcoded secrets ship a credential -- severity table
    # classifies this as Critical ("ships a secret"); keep in sync with that.
    (r"(password|secret|token|apikey)\s*[:=]\s*['\"][^'\"]{4,}['\"]",
     "Possible hardcoded credential -- use config or environment variables"),
]

HIGH_PATTERNS = [
    # Universal rule 8: skipped tests need a ticket reference.
    (r"\b(?:xit|xdescribe|test\.skip|it\.skip|@Ignore|@Disabled)\b(?!.*(?:JIRA|CXDSK|TODO|BUG|ISSUE|LV-))",
     "Skipped test without ticket reference (e.g., // LV-1234)"),

    # Universal rule 9: POM boundaries -- locators only in page objects.
    (r"page\.locator\s*\(", "page.locator() used in spec file -- POM violation: move locator to page object and expose via a method"),
    (r"driver\.findElement\s*\(", "driver.findElement() used in a test class -- POM violation: move to a page object"),

    # Universal rule 9 (other direction): value assertions belong in specs, not page objects.
    (r"expect\s*\([^)]*\)\s*\.\s*(?:toBe|toEqual|toContain|toBeTruthy|toBeFalsy|toBeGreaterThan|toBeLessThan|toHaveLength|toMatch|toHaveCount|not\.)",
     "Value assertion found in Page Object -- move to test file or return the value instead"),
    (r"(Assert\.\w+|assertThat)\s*\(", "Assertion found in Page Object -- move to the test class"),

    # Universal rule 11: fragile locators.
    (r"\.nth\s*\(\s*0\s*\)", "Index-based locator nth(0) -- use a stable, unique selector instead"),
    (r":first-child(?![a-zA-Z-])", "Index-based selector :first-child -- use a stable, unique selector instead"),
    (r"react-select-\d+-", "Auto-generated dynamic ID in locator -- use a stable attribute instead"),
    (r"//\w+/\w+/\w+\[", "Full absolute XPath detected -- use relative XPath or CSS selector"),

    # Universal rule 7: no hardcoded environment URLs.
    (r"https?://[a-zA-Z0-9._-]+\.(livevox|com|net|io)/", "Hardcoded URL -- import from config instead"),
]

MEDIUM_PATTERNS = [
    # Universal rule 10: no debug leftovers.
    (r"console\.(log|warn|error|info|debug)\s*\(", "console.log left in code -- remove before merging"),
    (r"System\.out\.print", "System.out.println left in code -- use the logging framework"),
    (r"^\s*print\s*\(", "print() left in code -- use the logging framework"),

    (r"waitForTimeout\s*\(\s*\d{1,3}\s*\)", "waitForTimeout usage -- prefer expect() auto-waiting"),
    (r"waitForTimeout\s*\(\s*\d{3}\s*\)", "waitForTimeout usage -- prefer expect() auto-waiting"),

    # Config import path convention (repo-wide, not framework-specific).
    (r"from\s+['\"]\.\.\/\.\.\/config(?!\/stg4|\/tst2)", "Config import not from src/config/stg4 or src/config/tst2"),

    (r"class\s+\w+Page\s+", "Page class detected -- verify it is placed under the pages/page-objects folder"),

    # No emojis / non-standard characters in comments (excludes box-drawing
    # separators and em/en-dash, which are common intentional decorators).
    (r"//(?!.*[─-╿—–]).*[^\x00-\x7F]", "Non-ASCII character in comment -- keep comments plain ASCII"),
]

LOW_PATTERNS = [
    # Universal rule 12: track TODO/FIXME/HACK with a ticket reference.
    (r"TODO|FIXME|HACK|XXX", "TODO/FIXME comment -- track in Jira with a ticket reference"),
]
