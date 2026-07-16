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
    # Java-specific blind sleeps not covered by core's Thread.sleep/time.sleep.
    Check("SEL-TIMEUNIT-SLEEP", "TimeUnit.*.sleep() detected -- use explicit waits (WebDriverWait/ExpectedConditions) instead of blind sleeps",
          "Use WebDriverWait + ExpectedConditions (explicit waits) instead of TimeUnit.*.sleep().",
          r"TimeUnit\.\w+\.sleep\s*\(", "any", frozenset()),

    # Broad catch with print-only handling can mask test failures -- distinct
    # from CORE-1 (literally empty catch block): this catch has a body, but
    # that body only prints and never rethrows/fails.
    Check("SEL-CATCH-PRINTSTACKTRACE", "catch(Exception) with printStackTrace() can mask failures -- rethrow or fail explicitly",
          "Rethrow the exception or fail the test explicitly instead of only printing the stack trace.",
          r"catch\s*\(\s*Exception\s+\w+\s*\)\s*\{\s*\w+\.printStackTrace\s*\(", "any", frozenset()),

    # Conditional assertions can pass vacuously when the guard is false.
    Check("SEL-VACUOUS-ASSERT", "Assertion guarded by isDisplayed/isEnabled/isSelected can pass vacuously when the branch does not execute",
          "Assert directly on the expected state instead of gating the assertion behind an if-guard.",
          r"if\s*\(\s*[^\n{}]*\.(isDisplayed|isEnabled|isSelected)\s*\(\s*\)\s*\)\s*\{\s*(Assert\.|assertThat\s*\()",
          "any", frozenset()),
]

HIGH_PATTERNS = [
    # driver.findElement and Assert-in-page-object are already covered by
    # qa-review-core (they are framework-agnostic POM-boundary rules stated
    # generically across languages). Selenium-specific additions:
    Check("SEL-XPATH-INDEX", "Index-based XPath detected -- use a stable, unique locator instead",
          "Use a stable, unique locator instead of an index-based XPath.",
          r"\(\s*\.\.\.\s*\)\[\d+\]", "any", frozenset()),

    # By.xpath(...) / @FindBy(xpath=...) absolute and index-based variants --
    # CORE-11's absolute-XPath pattern requires a literal "//" lead-in and
    # does not match a single-leading-slash absolute path like "/html/body/...",
    # so these are additive, not duplicates.
    Check("SEL-BYXPATH-ABSOLUTE", "Absolute XPath detected -- use a stable, relative locator instead",
          "Use a stable, relative locator instead of an absolute XPath.",
          r"By\.xpath\s*\(\s*['\"]\s*/html/", "any", frozenset()),
    Check("SEL-BYXPATH-INDEX", "Index-based XPath detected -- use a stable, unique locator instead",
          "Use a stable, unique locator instead of an index-based XPath.",
          r"By\.xpath\s*\(\s*['\"]\s*\(//.*\)\s*\[\d+\]", "any", frozenset()),
    Check("SEL-FINDBY-XPATH-ABSOLUTE", "Absolute XPath in @FindBy -- use stable relative locator strategy",
          "Use a stable, relative locator strategy in @FindBy instead of an absolute XPath.",
          r"@FindBy\s*\(\s*xpath\s*=\s*['\"]\s*/html/", "any", frozenset()),
    Check("SEL-FINDBY-XPATH-INDEX", "Index-based XPath in @FindBy -- use stable unique locator",
          "Use a stable, unique locator in @FindBy instead of an index-based XPath.",
          r"@FindBy\s*\(\s*xpath\s*=\s*['\"]\s*\(//.*\)\s*\[\d+\]", "any", frozenset()),

    Check("SEL-IGNORE-NOTICKET", "@Ignore without ticket reference (e.g., // LV-1234)",
          "Add a ticket reference (e.g. LV-1234) to the @Ignore.",
          r"@Ignore\b(?!.*(?:JIRA|CXDSK|TODO|BUG|ISSUE|LV-))\)?\s*\n\s*(public|private)?\s*(static)?\s*void",
          "any", frozenset()),

    # Hardcoded environment entrypoints in Selenium navigation -- complements
    # CORE-7 (which only recognizes a fixed TLD allowlist: livevox/com/net/io)
    # by catching any driver.get(...) literal URL regardless of domain suffix.
    Check("SEL-DRIVERGET-URL", "Hardcoded URL in driver.get() -- use config/environment variables",
          "Read the URL from config/environment instead of a literal in driver.get().",
          r"driver\.get\s*\(\s*['\"]https?://", "any", frozenset()),

    # Shared mutable state across tests causes cross-scenario coupling/flakiness.
    Check("SEL-STATIC-MUTABLE-STATE", "Shared mutable static state in test code -- isolate state per test/scenario",
          "Isolate state per test/scenario instead of sharing it via a static field.",
          r"\bstatic\s+(?!final\b)(?:WebDriver|String|Map|List|Set)\b", "any", frozenset()),

    # Implicit and explicit waits mixed on the same driver -- unpredictable timing.
    Check("SEL-MIXED-WAITS", "implicitlyWait() detected -- mixing implicit and explicit waits causes unpredictable timing",
          "Use explicit waits (WebDriverWait) exclusively; remove the implicit wait.",
          r"manage\(\)\.timeouts\(\)\.implicitlyWait", "any", frozenset()),

    # Java-specific bug-prone string comparison.
    Check("SEL-STRING-EQUALITY", "String compared with '==' -- use .equals(...) to avoid reference-comparison bugs",
          "Use .equals(...) instead of == to compare String values.",
          r"(?:\b\w+[\w.]*\s*==\s*\"[^\"]*\"|\"[^\"]*\"\s*==\s*\b\w+[\w.]*)",
          "any", frozenset()),
]

MEDIUM_PATTERNS = [
    # New WebDriver created per test method instead of a managed fixture.
    Check("SEL-NEW-DRIVER", "WebDriver instantiated directly in a test method -- use a managed fixture (@BeforeEach) instead",
          "Use a managed fixture (@BeforeEach/@AfterEach) instead of instantiating the driver per test.",
          r"new\s+(ChromeDriver|FirefoxDriver|RemoteWebDriver|EdgeDriver)\s*\(",
          "any", frozenset()),

    # Deprecated WebDriverWait constructor style still appears in older suites.
    Check("SEL-LEGACY-WEBDRIVERWAIT", "Legacy WebDriverWait(driver, seconds) style detected -- prefer Duration-based constructor",
          "Prefer the Duration-based WebDriverWait constructor over the legacy (driver, seconds) form.",
          r"new\s+WebDriverWait\s*\(\s*\w+\s*,\s*\d+\s*\)",
          "any", frozenset()),

    # Timing constants should be centralized, not duplicated inline. Fills the
    # "Raw Thread/timing constants scattered" gap previously listed as not
    # automated in SKILL.md.
    Check("SEL-HARDCODED-TIMING-CONST", "Hardcoded timing constant -- centralize wait configuration",
          "Centralize wait/timeout configuration instead of a local hardcoded constant.",
          r"\b(?:TIMEOUT|WAIT|SLEEP)_?[A-Z0-9_]*\s*=\s*\d{3,}",
          "any", frozenset()),

    # Explicit wait with inline literal duration should be centralized.
    Check("SEL-INLINE-DURATION-LITERAL", "WebDriverWait uses inline literal Duration -- prefer centralized timeout configuration",
          "Centralize the Duration value instead of an inline literal in WebDriverWait.",
          r"new\s+WebDriverWait\s*\(\s*\w+\s*,\s*Duration\.of(?:Seconds|Millis)\s*\(\s*\d+\s*\)",
          "any", frozenset()),

    # Java-specific: broad throws on tests hide specific failure contracts.
    Check("SEL-TEST-THROWS-EXCEPTION", "@Test method throws generic Exception -- prefer specific exceptions or assertion-based failure handling",
          "Prefer specific exception types or assertion-based failure handling over a generic throws Exception.",
          r"@Test[\s\S]{0,120}?public\s+void\s+\w+\s*\([^)]*\)\s*throws\s+Exception",
          "any", frozenset()),
    Check("SEL-THROWS-EXCEPTION", "Method throws generic Exception/Throwable -- prefer specific exception types",
          "Prefer specific exception types over a generic throws Exception/Throwable.",
          r"public\s+\w+[\w<>\[\]]*\s+\w+\s*\([^)]*\)\s*throws\s+(Exception|Throwable)",
          "any", frozenset()),

    # Java-specific: stack traces printed directly instead of logger/fail.
    Check("SEL-PRINTSTACKTRACE", "printStackTrace() used -- replace with structured logger and explicit test failure context",
          "Replace with a structured logger call and explicit test failure context.",
          r"\b\w+\.printStackTrace\s*\(", "any", frozenset()),

    # Java-specific: raw collections reduce type safety in test code.
    Check("SEL-RAW-COLLECTION", "Raw collection type detected -- use generics (e.g., List<String>) for type safety",
          "Use generics (e.g. List<String>) instead of a raw collection type.",
          r"\b(List|Map|Set|HashMap|ArrayList|HashSet)\s+\w+\s*=\s*new\s+\w+\s*\(",
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
    Check("SEL-GENERIC-TEST-NAME", "Insight: Generic test method name detected -- use an intent-revealing name",
          "Use an intent-revealing test method name.",
          r"@Test\s*\n\s*public\s+void\s+(verify|validate|check|run)\s*\(",
          "any", frozenset()),

    # Repeated maximize calls add noise and can hide responsive issues.
    Check("SEL-WINDOW-MAXIMIZE", "Insight: window().maximize() used in tests -- verify this is required and does not hide responsive behavior issues",
          "Verify window().maximize() is required here and is not masking a responsive-layout issue.",
          r"manage\(\)\.window\(\)\.maximize\s*\(", "any", frozenset()),

    # Java-specific style hygiene.
    Check("SEL-WILDCARD-IMPORT", "Insight: Wildcard import detected -- prefer explicit imports for readability",
          "Prefer explicit imports over a wildcard import.",
          r"^\s*import\s+[^;]*\.\*\s*;", "any", frozenset()),
]
