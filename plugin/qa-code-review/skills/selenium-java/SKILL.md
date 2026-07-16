---
name: selenium-java
description: Selenium + Java review overlay. Applied on top of qa-review-core when the repo is a Maven/Gradle project (pom.xml or build.gradle) that depends on selenium-java. Covers explicit-wait discipline, locator strategy, WebDriver lifecycle, and PageFactory/POM rules.
---

# Selenium + Java — Review Overlay

Applied together with `qa-review-core`.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/review.py` | Deterministic patterns for the Selenium/Java-specific rules below (`Thread.sleep`, empty catch, commented assertions, and empty `@Test` bodies are already covered generically by `qa-review-core/scripts/review.py`, as `CORE-2`/`CORE-1`/`CORE-4`/`CORE-5`). Merged by `deterministic_review.py` when this overlay is selected (detected via a Maven/Gradle build file). Review findings come only from these scripts — never from an LLM. |

## Critical

- **`Thread.sleep(...)`** — blind wait, primary cause of flakiness. Use
  `WebDriverWait` + `ExpectedConditions` (explicit waits). (`CORE-2`, from qa-review-core)
- **Swallowed exceptions** — empty `catch (Exception e) {}` or a bare
  `catch` that neither rethrows nor logs. (`CORE-1`, from qa-review-core)
- **Commented-out assertions** (`// Assert.` / `// assertEquals`). (`CORE-4`, from qa-review-core)
- **Empty `@Test` body.** (`CORE-5`, from qa-review-core)

## High

- **`driver.findElement` outside a page object** — POM violation; locators
  belong in page objects (`@FindBy` or a `By` constant), exposed via methods.
  Only fires outside a page object path -- calling `findElement` from within
  the page object itself is exactly where it belongs. (`CORE-9`, from qa-review-core)
- **Assertions inside a page object** — `Assert.*` / `assertThat` belong in the
  test, not the page object. (`CORE-9`, from qa-review-core)
- **Index-based XPath** `(...)[1]`. (`SEL-XPATH-INDEX`)
- **Fragile locators:** absolute XPath (`/html/body/div[2]/...`) — covered
  generically by `CORE-11`; locating by volatile auto-generated ids.
- **Hardcoded URLs** — use a properties file, env, or config class. (`CORE-7`, from qa-review-core.
  Hardcoded *credentials* are a separate `qa-review-core` rule and are
  **Critical**, not High — `CORE-6`; encrypted vault values are allowed.)
- **`@Ignore` / `@Disabled` without a ticket reference.** (`SEL-IGNORE-NOTICKET`
  for `@Ignore` specifically; `CORE-8` from qa-review-core also covers both
  generically.)
- **Implicit + explicit waits mixed** on the same driver — unpredictable timing. (`SEL-MIXED-WAITS`)

## Medium

- **`System.out.println`** debug output — use the logging framework (SLF4J/Log4j). (`CORE-10`, from qa-review-core)
- **New `WebDriver` created per test method** instead of a managed
  fixture/`@BeforeEach` + `@AfterEach` teardown — leaks browser sessions. (`SEL-NEW-DRIVER`)
- **Raw `Thread`/timing constants** scattered instead of centralized config.

> **Not currently automated:** missing `driver.quit()` in teardown, "Raw
> Thread/timing constants scattered", and missing `@DisplayName`/grouping
> tags (below) require whole-file/whole-class reasoning that the line-based
> regex engine can't do reliably. Treat these as manual-review guidance until
> a dedicated check is built, not as things the pipeline will flag.

## Low

- Test method names that do not describe intent. (`SEL-NONDESC-TEST-NAME`)
- Missing `@DisplayName` / grouping tags for CI filtering.

## Conventions

- Test classes under `src/test/java`, page objects under `src/main/java` (or the
  project's `pages` package). One locator strategy, documented and consistent.
