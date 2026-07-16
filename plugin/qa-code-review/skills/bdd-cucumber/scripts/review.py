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
]

FEATURE_MEDIUM_PATTERNS = [
    # Scenarios without tags.
    Check("BDD-FEATURE-TAG-INSIGHT", "Insight: verify this Scenario has a @tag (e.g. @smoke, @regression) for CI filtering",
          "Add a @tag (e.g. @smoke, @regression) for CI filtering.",
          r"^\s*Scenario(?:\s+Outline)?\s*:", "any", frozenset()),

    # Hardcoded data that should be a Scenario Outline Examples table.
    Check("BDD-FEATURE-HARDCODE", "Possible hardcoded data in a Gherkin step -- consider a Scenario Outline Examples table",
          "Consider a Scenario Outline Examples table instead of a literal value.",
          r"\b(Given|When|Then|And|But)\b.*\b\d{4,}\b", "any", frozenset()),
]

FEATURE_LOW_PATTERNS = [
    Check("BDD-FEATURE-NARRATIVE", "Insight: Feature file missing a narrative (As a / I want / So that)",
          "Add a narrative (As a / I want / So that) to the Feature.",
          r"^Feature:\s*$", "any", frozenset()),
]

# Patterns for step-definition source files (glue code).
STEP_HIGH_PATTERNS = [
    # Locators or waits embedded directly in a step definition.
    Check("BDD-STEP-LOCATOR", "Step definition embeds a locator directly -- call a page object method instead",
          "Call a page object method instead of embedding the locator here.",
          r"@(Given|When|Then)\([^)]*\)[\s\S]{0,200}?\b(By\.|page\.locator|driver\.findElement)\b",
          "any", frozenset()),
    Check("BDD-STEP-WAIT", "Step definition embeds a raw wait -- call a page object method that encapsulates the wait",
          "Call a page object method that encapsulates the wait instead.",
          r"@(Given|When|Then)\([^)]*\)[\s\S]{0,200}?(Thread\.sleep|waitForTimeout)\s*\(",
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
]

STEP_LOW_PATTERNS = []

# Backward-compatible names deterministic_review.py falls back to for any file
# extension it does not recognize as .feature (kept empty -- driver overlays
# already cover the source files under review; the feature-specific sets
# above are what make this overlay meaningful).
CRITICAL_PATTERNS = []
HIGH_PATTERNS = []
MEDIUM_PATTERNS = []
LOW_PATTERNS = []
