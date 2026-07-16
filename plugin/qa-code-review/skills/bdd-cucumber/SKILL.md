---
name: bdd-cucumber
description: BDD / Cucumber review overlay. Applied ADDITIVELY on top of qa-review-core and whichever driver overlay is active (selenium-java or playwright-*) whenever the repo contains .feature files. Covers Gherkin quality and step-definition discipline. This overlay composes; it does not replace the driver overlay.
---

# BDD / Cucumber — Review Overlay (composable)

This overlay is added **in addition to** the driver overlay. Example stacks:

- Selenium + Java + Cucumber -> `qa-review-core` + `selenium-java` + `bdd-cucumber`
- Playwright + JS + Cucumber -> `qa-review-core` + `playwright-js` + `bdd-cucumber`

So all driver-level rules still apply inside step definitions; the rules here
are specific to Gherkin and the feature/step boundary.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/review.py` | Deterministic patterns, split by file kind: `FEATURE_*_PATTERNS` run against `.feature` files, `STEP_*_PATTERNS` run against step-definition source files (path/name heuristics). Loaded additively by `deterministic_review.py` alongside `qa-review-core` and the active driver overlay whenever any `.feature` file exists in the repo. Review findings come only from this script — never from an LLM. |

## High

- **Business logic / assertions written in `.feature` files.** Gherkin describes
  behaviour, not implementation. Steps like `Then I click the button with id x`
  leak UI detail into the spec — keep steps declarative.
- **Step definitions containing locators or waits directly** — the step should
  call a page object / driver action, not embed `By`/`page.locator`/sleeps.
- **Shared mutable state between steps via static/global fields** — flaky across
  scenarios; use scenario scope / dependency injection (PicoContainer, etc.).

## Medium

- **Scenarios without tags** (`@smoke`, `@regression`) — cannot be filtered in CI.
- **Hardcoded data in Gherkin** that should be a `Scenario Outline` `Examples`
  table or external test data.
- **Multiple `@Before` hooks** in the same step-definition file — consider
  consolidating, or verify the ordering is genuinely intentional.

## Low

- Feature files without a clear `Feature:` narrative (As a / I want / So that).

> **Not currently automated:** ambiguous/duplicate step definitions (needs
> cross-file matching), `Background` overuse, Given/When/Then ordering, and
> inconsistent Gherkin phrasing all require whole-suite or semantic reasoning
> this line-based regex engine can't do reliably. Treat these as manual-review
> guidance, not pipeline checks.

## Conventions

- `.feature` files under `src/test/resources/features` (Java) or `features/`
  (JS); step definitions in the project's `steps`/`step_definitions` package.
- One step phrase -> one glue method. Reuse steps; do not clone them.
