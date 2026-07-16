#!/usr/bin/env python3
"""
bdd-cucumber -- deterministic patterns (Layer 1).

Applied ADDITIVELY on top of qa-review-core AND whichever driver overlay is
active, whenever the repo contains .feature files. Covers the Gherkin/glue
boundary specifically; driver-level rules (Playwright/Selenium) still apply
inside step definitions. No LLM involved.

Two pattern sets, keyed by whether deterministic_review.py is looking at a
.feature file or a step-definition source file (.java/.ts/.js) --
deterministic_review.py picks the right list based on the file extension it
is currently analyzing.

Each pattern is a Check(id, rule, suggestion, regex, scope, flags) -- see
qa-review-core/scripts/review.py's module docstring for the exact scope/flags
contract, which is shared across every skill. `scope` is unused for these
(file-kind selection already happens via FEATURE_*/STEP_* list membership),
so it is always "any" here.
"""

from collections import namedtuple

Check = namedtuple("Check", ["id", "rule", "suggestion", "regex", "scope", "flags"])

# Patterns for .feature files (Gherkin).
FEATURE_HIGH_PATTERNS = [
    # Business logic / assertions written in Gherkin -- leaks UI detail into the spec.
    Check("BDD-FEATURE-UI-LEAK", "Step leaks UI implementation detail (locator/id) into Gherkin -- keep steps declarative",
          "Keep steps declarative; move the UI detail into the step definition.",
          r"\b(Given|When|Then|And|But)\b.*\b(click|clicks|tap|taps)\b.*\b(button|link|icon)\s+(with\s+)?(id|xpath|css|selector)\b",
          "any", frozenset()),

    # Assertion vocabulary in Gherkin often indicates implementation detail leakage.
    Check("BDD-FEATURE-ASSERT-LEAK", "Assertion/implementation wording in .feature step -- keep Gherkin behavior-focused and leave assertions to glue/tests",
          "Keep the step behavior-focused; move assertion wording into the glue code or test.",
          r"\b(Given|When|Then|And|But)\b.*\b(assert|verify|validate|should\s+equal|equals?)\b",
          "any", frozenset()),

    # Explicit locator strategy terms in Gherkin indicate non-declarative steps.
    Check("BDD-FEATURE-LOCATOR-LEAK", "Locator strategy leaked into Gherkin step text -- move selector details to step definition/page object",
          "Move the selector detail into the step definition or page object.",
          r"\b(Given|When|Then|And|But)\b.*\b(xpath|css\s+selector|data-testid|id=|class=)\b",
          "any", frozenset()),
]

FEATURE_MEDIUM_PATTERNS = [
    # Scenarios without tags.
    Check("BDD-FEATURE-TAG-INSIGHT", "Insight: verify this Scenario has a @tag (e.g. @smoke, @regression) for CI filtering",
          "Add a @tag (e.g. @smoke, @regression) for CI filtering.",
          r"^\s*Scenario(?:\s+Outline)?\s*:", "any", frozenset()),

    # Background-heavy suites often hide setup complexity.
    Check("BDD-FEATURE-BACKGROUND", "Background block detected -- verify setup is minimal and does not hide scenario intent",
          "Verify the Background setup stays minimal and does not hide scenario intent.",
          r"^\s*Background\s*:", "any", frozenset()),

    # Hardcoded data that should be a Scenario Outline Examples table.
    Check("BDD-FEATURE-HARDCODE", "Possible hardcoded data in a Gherkin step -- consider a Scenario Outline Examples table",
          "Consider a Scenario Outline Examples table instead of a literal value.",
          r"\b(Given|When|Then|And|But)\b.*\b\d{4,}\b", "any", frozenset()),
]

FEATURE_LOW_PATTERNS = [
    Check("BDD-FEATURE-NARRATIVE", "Insight: Feature file missing a narrative (As a / I want / So that)",
          "Add a narrative (As a / I want / So that) to the Feature.",
          r"^Feature:\s*$", "any", frozenset()),

    # NOTE: a feature-file-scoped TODO/FIXME/HACK/XXX check was considered but
    # is not added here -- qa-review-core's CORE-12 (scope: "any") already
    # scans every reviewed file, .feature included, so a duplicate here would
    # only double-count the same line under two rule ids.
]

# Patterns for step-definition source files (glue code).
STEP_HIGH_PATTERNS = [
    # Locators or waits embedded directly in a step definition. Hook set
    # widened to include Before/After/BeforeStep/AfterStep (not just
    # Given/When/Then), and the lookahead window widened 200 -> 220 chars.
    Check("BDD-STEP-LOCATOR", "Step definition embeds a locator directly -- call a page object method instead",
          "Call a page object method instead of embedding the locator here.",
          r"@(Given|When|Then|And|But|Before|After|BeforeStep|AfterStep)\([^)]*\)[\s\S]{0,220}?\b(By\.|page\.locator|driver\.findElement)\b",
          "any", frozenset()),
    Check("BDD-STEP-WAIT", "Step definition embeds a raw wait -- call a page object method that encapsulates the wait",
          "Call a page object method that encapsulates the wait instead.",
          r"@(Given|When|Then|And|But|Before|After|BeforeStep|AfterStep)\([^)]*\)[\s\S]{0,220}?(Thread\.sleep|waitForTimeout|TimeUnit\.\w+\.sleep)\s*\(",
          "any", frozenset()),

    # Shared mutable state between steps via static/global fields.
    Check("BDD-STEP-STATIC-FIELD", "Static mutable field in step definitions -- flaky across scenarios; use scenario-scoped DI instead",
          "Use scenario-scoped dependency injection (PicoContainer, etc.) instead of a static field.",
          r"(public\s+)?static\s+(?!final\b)\w[\w<>\[\]]*\s+\w+\s*;",
          "any", frozenset()),
]

STEP_MEDIUM_PATTERNS = [
    Check("BDD-STEP-MULTI-BEFORE", "Insight: multiple @Before hooks -- consider consolidating or verify ordering is intentional",
          "Consolidate the @Before hooks, or verify the ordering is genuinely intentional.",
          r"@Before\b.*\n(?:.*\n){0,20}?.*@Before\b", "any", frozenset()),

    # NOTE: generic "throws Exception/Throwable", raw collection types, and
    # System.out.println in glue code were considered here but are not added
    # -- Cucumber glue code in this repo is always Java, which means the
    # selenium-java overlay (SEL-THROWS-EXCEPTION, SEL-RAW-COLLECTION, and
    # qa-review-core's CORE-10) is always loaded alongside this one and
    # already scans every file with scope: "any", step definitions included.
    # A duplicate copy here would only double-count the same line.
]

STEP_LOW_PATTERNS = [
    # Generic glue method names that hide step intent -- not covered elsewhere
    # (selenium-java's non-descriptive-name checks target @Test methods, not
    # @Given/@When/@Then glue methods).
    Check("BDD-STEP-GENERIC-NAME", "Insight: Generic glue method name -- prefer intent-revealing step method names",
          "Prefer an intent-revealing step method name.",
          r"@(Given|When|Then|And|But)\([^)]*\)\s*\n\s*public\s+void\s+(step|given|when|then|doStep)\w*\s*\(",
          "any", frozenset()),

    # NOTE: a step-definition-scoped wildcard-import check was considered but
    # is not added here -- selenium-java's SEL-WILDCARD-IMPORT (scope: "any")
    # already covers every Java file, step definitions included.
]

# Backward-compatible names deterministic_review.py also merges globally
# (there is no separate feature_critical/step_critical bucket, so anything
# placed here applies to every reviewed file -- keep entries scoped tightly
# enough in their own regex to avoid false positives elsewhere).
CRITICAL_PATTERNS = [
    # Empty Cucumber step-definition body -- a real gap, not a duplicate:
    # CORE-5 (qa-review-core) only matches empty JS it/test() bodies or empty
    # @Test bodies, never an empty @Given/@When/@Then method, so without this
    # check an empty step definition passes every existing rule silently.
    Check("BDD-STEP-EMPTY-BODY", "Step definition has an empty method body -- scenario step has no executable behavior",
          "Implement the step's behavior or remove the step -- an empty body passes meaninglessly.",
          r"@(Given|When|Then|And|But)\([^)]*\)\s*(public\s+)?void\s+\w+\s*\([^)]*\)\s*\{\s*\}",
          "any", frozenset()),

    # NOTE: step-scoped duplicates of blind-sleep/wait and catch+printStackTrace
    # detection were considered for this global list but are not added --
    # qa-review-core's CORE-2/CORE-1 (scope: "any") and selenium-java's new
    # SEL-TIMEUNIT-SLEEP/SEL-CATCH-PRINTSTACKTRACE (scope: "any") already fire
    # on these lines regardless of file kind, so a step-scoped copy here would
    # double-count the same line under a third rule id. BDD-STEP-WAIT (High,
    # above) already extends coverage to TimeUnit.*.sleep within step bodies
    # without introducing that duplication.
]
HIGH_PATTERNS = []
MEDIUM_PATTERNS = []
LOW_PATTERNS = []
