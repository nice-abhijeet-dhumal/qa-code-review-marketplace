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
| `scripts/review.py` | Deterministic patterns, split by file kind: `FEATURE_*_PATTERNS` run against `.feature` files, `STEP_*_PATTERNS` run against step-definition source files (path/name heuristics). Each pattern is a `Check(id, rule, suggestion, regex, scope, flags)` namedtuple, same shape as every other skill. Loaded additively by `deterministic_review.py` alongside `qa-review-core` and the active driver overlay whenever any `.feature` file exists in the repo. Review findings come only from this script — never from an LLM. |

## Critical

- **Blind waits in step definitions** (`Thread.sleep`, `TimeUnit.*.sleep`,
  `waitForTimeout`) and glue hooks are critical flakiness sources. These are treated as
  Critical by `qa-review-core` (`CORE-2`) and `selenium-java` (`SEL-TIMEUNIT-SLEEP`)
  and should never be committed in glue code; `BDD-STEP-WAIT` (High, below)
  additionally flags them specifically within a step's body.
- **Swallowed exceptions in glue code** (`catch {}` / broad error masking)
  can let scenarios pass incorrectly. Treat as merge-blocking. (`CORE-1`;
  `catch (Exception)` with only `printStackTrace()` is `SEL-CATCH-PRINTSTACKTRACE`
  from `selenium-java`.)
- **Empty/invalid executable behavior in scenarios** (no meaningful
  Given/When/Then flow) should be treated as critical quality failure.
- **Empty step-definition body** (`@Given/@When/@Then ... {}` with no
  executable logic) is a critical behavior gap. `CORE-5` only matches empty
  JS `it/test()` bodies or empty `@Test` bodies, never an empty step method,
  so this is covered here instead. (`BDD-STEP-EMPTY-BODY`)

## High

- **Business logic / assertions written in `.feature` files.** Gherkin describes
  behaviour, not implementation. Steps like `Then I click the button with id x`
  leak UI detail into the spec — keep steps declarative. (`BDD-FEATURE-UI-LEAK`)
- **Assertion vocabulary in `.feature` steps** (`assert`, `verify`, `validate`,
  `should equal`) — keep Gherkin behavior-focused; leave assertions to
  glue/tests. (`BDD-FEATURE-ASSERT-LEAK`)
- **Locator strategy terms in `.feature` steps** (`xpath`, `css selector`,
  `data-testid`, `id=`, `class=`) — move selector detail to the step
  definition or page object. (`BDD-FEATURE-LOCATOR-LEAK`)
- **Step definitions containing locators or waits directly** — the step should
  call a page object / driver action, not embed `By`/`page.locator`/sleeps.
  Covers `Given`/`When`/`Then`/`And`/`But`/`Before`/`After`/`BeforeStep`/`AfterStep`
  hooks. (`BDD-STEP-LOCATOR`, `BDD-STEP-WAIT`)
- **Shared mutable state between steps via static/global fields** — flaky across
  scenarios; use scenario scope / dependency injection (PicoContainer, etc.). (`BDD-STEP-STATIC-FIELD`)
- **Step definitions that catch broad `Exception` and only print stack traces**
  can mask failures; fail/rethrow explicitly. (`SEL-CATCH-PRINTSTACKTRACE`, from
  `selenium-java` — already fires on step-definition files with scope `"any"`,
  so it is not duplicated here.)

## Medium

- **Scenarios without tags** (`@smoke`, `@regression`) — cannot be filtered in CI. (`BDD-FEATURE-TAG-INSIGHT`)
- **`Background` usage** should stay minimal and explicit; avoid hiding setup. (`BDD-FEATURE-BACKGROUND`)
- **Hardcoded data in Gherkin** that should be a `Scenario Outline` `Examples`
  table or external test data. (`BDD-FEATURE-HARDCODE`)
- **Multiple `@Before` hooks** in the same step-definition file — consider
  consolidating, or verify the ordering is genuinely intentional. (`BDD-STEP-MULTI-BEFORE`)
- **Generic `throws Exception/Throwable` in step definitions** — prefer
  specific exceptions. Covered by `selenium-java`'s `SEL-THROWS-EXCEPTION`
  (scope `"any"`, already applies to step-definition files) — not duplicated here.
- **Raw collection types in step definitions** (`List x = new ArrayList()`) —
  use generics for type safety. Covered by `selenium-java`'s `SEL-RAW-COLLECTION`
  — not duplicated here.
- **`System.out.println` in glue code** — prefer structured logging and
  explicit failure behavior. Covered by `qa-review-core`'s `CORE-10` — not
  duplicated here.

## Low (insights, non-blocking)

- Feature files without a clear `Feature:` narrative (As a / I want / So that). (`BDD-FEATURE-NARRATIVE`)
- TODO/FIXME/HACK without ticket context in feature/step files. Covered
  project-wide by `qa-review-core`'s `CORE-12` — not duplicated here.
- Wildcard imports in step-definition code. Covered by `selenium-java`'s
  `SEL-WILDCARD-IMPORT` — not duplicated here.
- Generic glue method names (`step`, `doStep`, `givenX`) that hide intent. (`BDD-STEP-GENERIC-NAME`)

> **Not currently automated:** ambiguous/duplicate step definitions (needs
> cross-file matching), `Background` overuse, Given/When/Then ordering, and
> inconsistent Gherkin phrasing all require whole-suite or semantic reasoning
> this line-based regex engine can't do reliably. Treat these as manual-review
> guidance, not pipeline checks.

## Conventions

- `.feature` files under `src/test/resources/features` (Java) or `features/`
  (JS); step definitions in the project's `steps`/`step_definitions` package.
- One step phrase -> one glue method. Reuse steps; do not clone them.
