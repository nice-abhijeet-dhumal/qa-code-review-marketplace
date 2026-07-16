#!/usr/bin/env python3
"""
selenium-java -- deterministic patterns (Layer 1).

Applied ON TOP of qa-review-core when the repo is a Maven/Gradle project
using Selenium. `Thread.sleep`, empty catch, commented assertions, and empty
test bodies are already covered generically by qa-review-core -- this module
only adds Selenium/Java-specific rules. No LLM involved.
"""

CRITICAL_PATTERNS = [
    # Nothing Selenium-Java-specific beyond qa-review-core's universal rules
    # (Thread.sleep, empty catch, commented assertions, empty @Test bodies).
]

HIGH_PATTERNS = [
    # driver.findElement and Assert-in-page-object are already covered by
    # qa-review-core (they are framework-agnostic POM-boundary rules stated
    # generically across languages). Selenium-specific additions:
    (r"\(\s*\.\.\.\s*\)\[\d+\]", "Index-based XPath detected -- use a stable, unique locator instead"),

    (r"@Ignore\b(?!.*(?:JIRA|CXDSK|TODO|BUG|ISSUE|LV-))\)?\s*\n\s*(public|private)?\s*(static)?\s*void",
     "@Ignore without ticket reference (e.g., // LV-1234)"),

    # Implicit and explicit waits mixed on the same driver -- unpredictable timing.
    (r"manage\(\)\.timeouts\(\)\.implicitlyWait", "implicitlyWait() detected -- mixing implicit and explicit waits causes unpredictable timing"),
]

MEDIUM_PATTERNS = [
    # New WebDriver created per test method instead of a managed fixture.
    (r"new\s+(ChromeDriver|FirefoxDriver|RemoteWebDriver|EdgeDriver)\s*\(",
     "WebDriver instantiated directly in a test method -- use a managed fixture (@BeforeEach) instead"),

    # Missing driver.quit() in teardown -- leaks processes. Heuristic: driver.quit()
    # missing entirely in a file that constructs a driver is checked at file level
    # by deterministic_review.py (Selenium-specific file-level rule), not per-line here.
]

LOW_PATTERNS = [
    # Test method names that do not describe intent (single-word or generic).
    (r"public\s+void\s+test\d*\s*\(", "Insight: Test method name is not descriptive -- name it after the behaviour under test"),
]
