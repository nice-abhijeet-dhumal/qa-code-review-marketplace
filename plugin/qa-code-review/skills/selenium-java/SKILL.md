---
name: selenium-java
description: Selenium + Java review overlay. Applied on top of qa-review-core when the repo is a Maven/Gradle project (pom.xml or build.gradle) that depends on selenium-java. Covers explicit-wait discipline, locator strategy, WebDriver lifecycle, and PageFactory/POM rules.
---

# Selenium + Java — Review Overlay

Applied together with `qa-review-core`.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/review.py` | Deterministic patterns for the Selenium/Java-specific rules below (`Thread.sleep`, empty catch, commented assertions, and empty `@Test` bodies are already covered generically by `qa-review-core/scripts/review.py`). Merged by `deterministic_review.py` when this overlay is selected (detected via a Maven/Gradle build file). Review findings come only from these scripts — never from an LLM. |

## Critical

- **`Thread.sleep(...)`** — blind wait, primary cause of flakiness. Use
  `WebDriverWait` + `ExpectedConditions` (explicit waits).
- **Swallowed exceptions** — empty `catch (Exception e) {}` or a bare
  `catch` that neither rethrows nor logs.
- **Commented-out assertions** (`// Assert.` / `// assertEquals`).
- **Empty `@Test` body.**

## High

- **`driver.findElement` in a test class** — POM violation; locators belong in
  page objects (`@FindBy` or a `By` constant), exposed via methods.
- **Assertions inside a page object** — `Assert.*` / `assertThat` belong in the
  test, not the page object.
- **Fragile locators:** absolute XPath (`/html/body/div[2]/...`), index-based
  XPath (`(...)[1]`), or locating by volatile auto-generated ids.
- **Hardcoded credentials / URLs** — use a properties file, env, or config class.
- **`@Ignore` / `@Disabled` without a ticket reference.**
- **Implicit + explicit waits mixed** on the same driver — unpredictable timing.

## Medium

- **`System.out.println`** debug output — use the logging framework (SLF4J/Log4j).
- **New `WebDriver` created per test method** instead of a managed
  fixture/`@BeforeEach` + `@AfterEach` teardown — leaks browser sessions.
- **Missing `driver.quit()`** in teardown — leaks processes.
- **Raw `Thread`/timing constants** scattered instead of centralized config.

## Low

- Test method names that do not describe intent.
- Missing `@DisplayName` / grouping tags for CI filtering.

## Conventions

- Test classes under `src/test/java`, page objects under `src/main/java` (or the
  project's `pages` package). One locator strategy, documented and consistent.
