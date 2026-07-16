#!/usr/bin/env python3
"""
selenium-java -- deterministic patterns (Layer 1).

Applied ON TOP of qa-review-core when the repo is a Maven/Gradle project
using Selenium. `Thread.sleep`, empty catch, commented assertions, and empty
test bodies are already covered generically by qa-review-core -- this module
only adds Selenium/Java-specific rules. No LLM involved.

Each pattern is a Check(id, rule, suggestion, regex, scope, flags) -- see
qa-review-core/scripts/review.py's module docstring for the exact scope/flags
contract, which is shared across every skill.
"""

from collections import namedtuple

Check = namedtuple("Check", ["id", "rule", "suggestion", "regex", "scope", "flags"])

CRITICAL_PATTERNS = [
    # Nothing Selenium-Java-specific beyond qa-review-core's universal rules
    # (Thread.sleep, empty catch, commented assertions, empty @Test bodies).
]

HIGH_PATTERNS = [
    # driver.findElement and Assert-in-page-object are already covered by
    # qa-review-core (they are framework-agnostic POM-boundary rules stated
    # generically across languages). Selenium-specific additions:
    Check("SEL-XPATH-INDEX", "Index-based XPath detected -- use a stable, unique locator instead",
          "Use a stable, unique locator instead of an index-based XPath.",
          r"\(\s*\.\.\.\s*\)\[\d+\]", "any", frozenset()),

    Check("SEL-IGNORE-NOTICKET", "@Ignore without ticket reference (e.g., // LV-1234)",
          "Add a ticket reference (e.g. LV-1234) to the @Ignore.",
          r"@Ignore\b(?!.*(?:JIRA|CXDSK|TODO|BUG|ISSUE|LV-))\)?\s*\n\s*(public|private)?\s*(static)?\s*void",
          "any", frozenset()),

    # Implicit and explicit waits mixed on the same driver -- unpredictable timing.
    Check("SEL-MIXED-WAITS", "implicitlyWait() detected -- mixing implicit and explicit waits causes unpredictable timing",
          "Use explicit waits (WebDriverWait) exclusively; remove the implicit wait.",
          r"manage\(\)\.timeouts\(\)\.implicitlyWait", "any", frozenset()),
]

MEDIUM_PATTERNS = [
    # New WebDriver created per test method instead of a managed fixture.
    Check("SEL-NEW-DRIVER", "WebDriver instantiated directly in a test method -- use a managed fixture (@BeforeEach) instead",
          "Use a managed fixture (@BeforeEach/@AfterEach) instead of instantiating the driver per test.",
          r"new\s+(ChromeDriver|FirefoxDriver|RemoteWebDriver|EdgeDriver)\s*\(",
          "any", frozenset()),

    # NOTE: "missing driver.quit() in teardown" is intentionally NOT a pattern
    # here -- it requires whole-file reasoning (driver constructed somewhere,
    # .quit() absent everywhere) that this line-based regex engine can't do
    # reliably. See selenium-java/SKILL.md's "Not currently automated" note.
]

LOW_PATTERNS = [
    # Test method names that do not describe intent (single-word or generic).
    Check("SEL-NONDESC-TEST-NAME", "Insight: Test method name is not descriptive -- name it after the behaviour under test",
          "Name the test method after the behaviour under test.",
          r"public\s+void\s+test\d*\s*\(", "any", frozenset()),
]
