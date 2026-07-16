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
- **`TimeUnit.*.sleep(...)`** — still a blind wait; use explicit waits instead. (`SEL-TIMEUNIT-SLEEP`)
- **Swallowed exceptions** — empty `catch (Exception e) {}` or a bare
  `catch` that neither rethrows nor logs. (`CORE-1`, from qa-review-core)
- **`catch (Exception)` with only `printStackTrace()`** — the catch body is
  not empty, but it never rethrows or fails the test, so failures are masked
  just as effectively. (`SEL-CATCH-PRINTSTACKTRACE`)
- **Assertions guarded by `isDisplayed`/`isEnabled`/`isSelected` branches** can
  pass vacuously when the guard is false; assert directly on expected state. (`SEL-VACUOUS-ASSERT`)
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
- **`By.xpath(...)` absolute or index-based XPath**, and the same in
  `@FindBy(xpath = ...)`. `CORE-11`'s absolute-XPath pattern requires a `//`
  lead-in and does not match a single-leading-slash path like `/html/body/...`,
  so these are additive coverage, not duplicates. (`SEL-BYXPATH-ABSOLUTE`,
  `SEL-BYXPATH-INDEX`, `SEL-FINDBY-XPATH-ABSOLUTE`, `SEL-FINDBY-XPATH-INDEX`)
- **Hardcoded URLs** — use a properties file, env, or config class. (`CORE-7`, from qa-review-core.
  Hardcoded *credentials* are a separate `qa-review-core` rule and are
  **Critical**, not High — `CORE-6`; encrypted vault values are allowed.)
- **Hardcoded URL literal in `driver.get(...)`** — complements `CORE-7`, which
  only recognizes a fixed TLD allowlist (`livevox`/`com`/`net`/`io`); this
  catches any `driver.get("https://...")` regardless of domain suffix, so the
  two rules overlap for common TLDs and are additive for others. (`SEL-DRIVERGET-URL`)
- **`@Ignore` / `@Disabled` without a ticket reference.** (`SEL-IGNORE-NOTICKET`
  for `@Ignore` specifically; `CORE-8` from qa-review-core also covers both
  generically, so a standalone `@Disabled` rule is not duplicated here.)
- **Implicit + explicit waits mixed** on the same driver — unpredictable timing. (`SEL-MIXED-WAITS`)
- **Shared mutable static state** (`static` non-final `WebDriver`/`String`/`Map`/
  `List`/`Set` fields) — causes cross-scenario coupling/flakiness. (`SEL-STATIC-MUTABLE-STATE`)
- **String compared with `==`** instead of `.equals(...)` — reference-comparison
  bug risk in Java. (`SEL-STRING-EQUALITY`)

## Medium

- **`System.out.println`** debug output — use the logging framework (SLF4J/Log4j). (`CORE-10`, from qa-review-core)
- **New `WebDriver` created per test method** instead of a managed
  fixture/`@BeforeEach` + `@AfterEach` teardown — leaks browser sessions. (`SEL-NEW-DRIVER`)
- **Legacy `WebDriverWait(driver, seconds)` style** — prefer Duration-based
  constructor for modern Selenium APIs. (`SEL-LEGACY-WEBDRIVERWAIT`)
- **Raw timing constants** (`TIMEOUT_*`/`WAIT_*`/`SLEEP_*` = a 3+-digit literal)
  scattered instead of centralized config. (`SEL-HARDCODED-TIMING-CONST`)
- **Inline `Duration.ofSeconds(...)`/`Duration.ofMillis(...)` literals** in
  `WebDriverWait` construction — prefer centralized timeout config. (`SEL-INLINE-DURATION-LITERAL`)
- **`@Test` method / any method throwing generic `Exception`/`Throwable`** —
  hides the specific failure contract; prefer specific exceptions or
  assertion-based failure handling. (`SEL-TEST-THROWS-EXCEPTION`, `SEL-THROWS-EXCEPTION`)
- **`printStackTrace()` used on its own** (outside the Critical catch+print
  combination above) — replace with structured logging and explicit failure
  context. (`SEL-PRINTSTACKTRACE`)
- **Raw collection types** (`List`/`Map`/`Set`/`HashMap`/`ArrayList`/`HashSet`
  declared without generics) — use generics for type safety. (`SEL-RAW-COLLECTION`)

> **Not currently automated:** missing `driver.quit()` in teardown, and
> missing `@DisplayName`/grouping tags require whole-file/whole-class
> reasoning that the line-based regex engine can't do reliably. Treat these as
> manual-review guidance until a dedicated check is built, not as things the
> pipeline will flag.

## Low (insights, non-blocking)

- Test method names that do not describe intent. (`SEL-NONDESC-TEST-NAME`)
- Generic test method names (`verify`/`validate`/`check`/`run`). (`SEL-GENERIC-TEST-NAME`)
- Repeated `window().maximize()` usage in tests (verify it is necessary and not
  hiding responsive behavior issues). (`SEL-WINDOW-MAXIMIZE`)
- Wildcard imports (`import ...*;`). (`SEL-WILDCARD-IMPORT`)
- Missing `@DisplayName` / grouping tags for CI filtering.

## Automated Rule Coverage (This Skill Script)

These are enforced by `scripts/review.py` for Selenium-specific checks,
in addition to `qa-review-core/scripts/review.py`.

- Critical:
  - `SEL-TIMEUNIT-SLEEP` — `TimeUnit.*.sleep(...)` blind waits
  - `SEL-CATCH-PRINTSTACKTRACE` — `catch(Exception)` + `printStackTrace()` failure masking
  - `SEL-VACUOUS-ASSERT` — assertions gated by `isDisplayed`/`isEnabled`/`isSelected` branch checks
- High:
  - `SEL-XPATH-INDEX`, `SEL-BYXPATH-ABSOLUTE`, `SEL-BYXPATH-INDEX`,
    `SEL-FINDBY-XPATH-ABSOLUTE`, `SEL-FINDBY-XPATH-INDEX` — absolute/index-based XPath
  - `SEL-DRIVERGET-URL` — hardcoded URL in `driver.get(...)`
  - `SEL-IGNORE-NOTICKET` — `@Ignore` without ticket
  - `SEL-MIXED-WAITS` — `implicitlyWait(...)` usage warning (mix-risk with explicit waits)
  - `SEL-STATIC-MUTABLE-STATE` — shared mutable static state
  - `SEL-STRING-EQUALITY` — Java string comparison using `==` instead of `.equals(...)`
- Medium:
  - `SEL-NEW-DRIVER` — direct driver instantiation in tests
  - `SEL-LEGACY-WEBDRIVERWAIT` — legacy `WebDriverWait(driver, seconds)` constructor
  - `SEL-HARDCODED-TIMING-CONST` — hardcoded timeout/wait constants
  - `SEL-INLINE-DURATION-LITERAL` — inline `Duration.ofSeconds(...)`/`Duration.ofMillis(...)` literals in `WebDriverWait`
  - `SEL-TEST-THROWS-EXCEPTION`, `SEL-THROWS-EXCEPTION` — generic `throws Exception/Throwable` usage
  - `SEL-PRINTSTACKTRACE` — `printStackTrace()` usage in test code
  - `SEL-RAW-COLLECTION` — raw collection types without generics
- Low:
  - `SEL-NONDESC-TEST-NAME`, `SEL-GENERIC-TEST-NAME` — generic/non-descriptive test method names
  - `SEL-WINDOW-MAXIMIZE` — `window().maximize()` usage insight
  - `SEL-WILDCARD-IMPORT` — wildcard imports (`import ...*;`)

> **Deliberately not duplicated:** a bare `react-select-\d+` dynamic-ID check
> and a standalone `@Disabled`-without-ticket check were considered but are
> already covered project-wide by `CORE-11` and `CORE-8` respectively (both
> `scope: "any"`), so adding Selenium-specific copies would only double-count
> the same line under two rule ids.

## Conventions

- Test classes under `src/test/java`, page objects under `src/main/java` (or the
  project's `pages` package). One locator strategy, documented and consistent.
