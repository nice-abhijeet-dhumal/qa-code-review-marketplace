#!/usr/bin/env python3
"""
bdd-cucumber -- deterministic patterns (Layer 1).

Applied ADDITIVELY on top of qa-review-core AND whichever driver overlay is
active, whenever the repo contains .feature files. Covers the Gherkin/glue
boundary specifically; driver-level rules (Playwright/Selenium) still apply
inside step definitions. No LLM involved.

Two pattern sets, keyed by whether engine.py is looking at a .feature file
or a step-definition source file (.java/.ts/.js) -- engine.py picks the
right list based on the file extension it is currently analyzing.
"""

# Patterns for .feature files (Gherkin).
FEATURE_HIGH_PATTERNS = [
    # Business logic / assertions written in Gherkin -- leaks UI detail into the spec.
    (r"\b(Given|When|Then|And|But)\b.*\b(click|clicks|tap|taps)\b.*\b(button|link|icon)\s+(with\s+)?(id|xpath|css|selector)\b",
     "Step leaks UI implementation detail (locator/id) into Gherkin -- keep steps declarative"),
]

FEATURE_MEDIUM_PATTERNS = [
    # Scenarios without tags.
    (r"^\s*Scenario(?:\s+Outline)?\s*:", "Insight: verify this Scenario has a @tag (e.g. @smoke, @regression) for CI filtering"),

    # Hardcoded data that should be a Scenario Outline Examples table.
    (r"\b(Given|When|Then|And|But)\b.*\b\d{4,}\b", "Possible hardcoded data in a Gherkin step -- consider a Scenario Outline Examples table"),
]

FEATURE_LOW_PATTERNS = [
    (r"^Feature:\s*$", "Insight: Feature file missing a narrative (As a / I want / So that)"),
]

# Patterns for step-definition source files (glue code).
STEP_HIGH_PATTERNS = [
    # Locators or waits embedded directly in a step definition.
    (r"@(Given|When|Then)\([^)]*\)[\s\S]{0,200}?\b(By\.|page\.locator|driver\.findElement)\b",
     "Step definition embeds a locator directly -- call a page object method instead"),
    (r"@(Given|When|Then)\([^)]*\)[\s\S]{0,200}?(Thread\.sleep|waitForTimeout)\s*\(",
     "Step definition embeds a raw wait -- call a page object method that encapsulates the wait"),

    # Shared mutable state between steps via static/global fields.
    (r"(public\s+)?static\s+(?!final\b)\w[\w<>\[\]]*\s+\w+\s*;",
     "Static mutable field in step definitions -- flaky across scenarios; use scenario-scoped DI instead"),
]

STEP_MEDIUM_PATTERNS = [
    (r"@Before\b.*\n(?:.*\n){0,20}?.*@Before\b", "Insight: multiple @Before hooks -- consider consolidating or verify ordering is intentional"),
]

STEP_LOW_PATTERNS = []

# Backward-compatible names engine.py falls back to for any file extension it
# does not recognize as .feature (kept empty -- driver overlays already cover
# the source files under review; the feature-specific sets above are what
# make this overlay meaningful).
CRITICAL_PATTERNS = []
HIGH_PATTERNS = []
MEDIUM_PATTERNS = []
LOW_PATTERNS = []
