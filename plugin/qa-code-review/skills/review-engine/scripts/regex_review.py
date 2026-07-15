#!/usr/bin/env python3
"""
QA Automation Code Review -- Multi-Mode Runner

Supports three review modes:
  1. PR/MR mode    -- triggered automatically on every GitHub PR or GitLab MR
  2. Commit mode   -- review a single specific commit by SHA
  3. Repo mode     -- review all matching source files in the full repository

Mode is selected via the REVIEW_MODE environment variable:
  REVIEW_MODE=pr      (default when running inside CI on a PR/MR event)
  REVIEW_MODE=commit  (requires COMMIT_SHA)
  REVIEW_MODE=repo    (scans entire working directory)

Environment Variables:

  Common:
    REVIEW_MODE    -- "pr" | "commit" | "repo"  (default: pr)
    CI_SOURCE      -- "gitlab" | "github"  (auto-detected from CI env)

  GitLab (all modes):
    GITLAB_API_URL                -- e.g. https://vcs.build.livevox.net/api/v4
    GITLAB_PERSONAL_ACCESS_TOKEN  -- PAT with api scope
    CI_PROJECT_ID                 -- auto-set by GitLab CI

  GitLab PR mode (auto-set by GitLab CI):
    CI_MERGE_REQUEST_IID

  GitLab commit mode:
    COMMIT_SHA     -- full or short commit SHA to review

  GitHub (all modes):
    GITHUB_TOKEN        -- auto-set by GitHub Actions
    GITHUB_REPOSITORY   -- owner/repo  (auto-set by GitHub Actions)

  GitHub PR mode (auto-set by GitHub Actions):
    PR_NUMBER

  GitHub commit mode:
    COMMIT_SHA     -- full or short commit SHA to review

  Repo mode (both platforms):
    REPO_ROOT      -- absolute path to repo root (default: current directory)
"""

import os
import re
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# ----------------------------------------------------------------------------
# REVIEW RULES
# Aligned with copilot-instructions.md and this repo's automation standards.
# ----------------------------------------------------------------------------

CRITICAL_PATTERNS = [
    # Commented-out assertion calls (must have parenthesis indicating a real call)
    (r"//\s*(expect|assert|Assert\.|should)\s*[\.(]", "Commented-out assertion"),
    (r"(it|test)\s*\([^)]*,\s*(\(\s*\)|async\s*\(\s*\))\s*=>\s*\{\s*\}\s*\)", "Empty test body"),

    # Hardcoded waits -- Critical in spec files, downgraded in _check_line for page objects
    (r"waitForTimeout\s*\(\s*\d{4,}", "Hardcoded waitForTimeout > 1s -- use waitFor/expect assertions"),
    (r"waitForTimeout\s*\(\s*[1-9]\d{3,}", "Hardcoded waitForTimeout > 1s -- use waitFor/expect assertions"),
    (r"Thread\.sleep\s*\(", "Thread.sleep -- use explicit Playwright waits"),

    # Empty catch blocks swallowing errors
    (r"catch\s*\([^)]*\)\s*\{\s*\}", "Empty catch block swallowing errors"),
    (r"catch\s*\{\s*\}", "Empty catch block swallowing errors"),

    # page.pause() committed -- will hang CI indefinitely by launching Playwright Inspector
    (r"page\.pause\s*\(\s*\)", "page.pause() committed -- remove before merging, it hangs CI"),

    # Unawaited Playwright actions -- silently no-op in TypeScript
    # Uses line-level check: only flags if 'await' does NOT appear anywhere on the same line
    (r"(?!.*\bawait\b).*\.page\.(goto|click|fill|check|uncheck|selectOption|hover|dblclick|tap|press|type|setInputFiles|dragAndDrop)\s*\(", "Possible missing await on Playwright page action -- unawaited actions silently no-op"),

    # Playwright test framework imports inside page object files
    # Acceptable: import { Page, expect } or { Locator, expect } (expect used for waits)
    # Not acceptable: import { test } or import { expect } without Page/Locator
    (r"import\s+\{[^}]*\}\s+from\s+['\"]@playwright/test['\"]", "Playwright test framework imported without Page type -- verify this is needed"),

    # Nested test() inside another test() body -- causes Playwright runtime error
    # Note: test() inside test.describe() is valid and must NOT be flagged.
    # This pattern is intentionally NOT in CRITICAL_PATTERNS -- it is handled
    # with context-aware logic in analyze_file_content / analyze_diff instead.
    # (kept as a comment reference only)
]

HIGH_PATTERNS = [
    # Skipped tests without a Jira ticket reference
    (r"\b(?:xit|xdescribe|test\.skip|it\.skip|@Ignore|@Disabled)\b(?!.*(?:JIRA|CXDSK|TODO|BUG|ISSUE|LV-))", "Skipped test without ticket reference (e.g., // LV-1234)"),

    # Hardcoded test data in spec files
    (r"(page\.fill|sendKeys|\.type)\s*\([^,]+,\s*['\"](?!.*\$|.*\{).{5,}['\"]", "Possible hardcoded test data in spec -- use testdata or config"),

    # Value assertions inside page object classes (POM violation)
    # Note: expect(locator).toBeVisible/toBeHidden/toBeEnabled are acceptable as wait mechanisms.
    # Only flag expect() used for VALUE assertions (toBe, toContain, toEqual, toBeTruthy, etc.)
    (r"expect\s*\([^)]*\)\s*\.\s*(?:toBe|toEqual|toContain|toBeTruthy|toBeFalsy|toBeGreaterThan|toBeLessThan|toHaveLength|toMatch|toHaveCount|not\.)", "Value assertion found in Page Object -- move to test file or return the value instead"),

    # Index-based locators (fragile selectors)
    (r"\.nth\s*\(\s*0\s*\)", "Index-based locator nth(0) -- use a stable, unique selector instead"),
    (r":first-child(?![a-zA-Z-])", "Index-based selector :first-child -- use a stable, unique selector instead"),

    # Dynamic/auto-generated IDs (fragile)
    (r"react-select-\d+-", "Auto-generated dynamic ID in locator -- use a stable attribute instead"),

    # Full absolute XPath (fragile)
    (r"//\w+/\w+/\w+\[", "Full absolute XPath detected -- use relative XPath or CSS selector"),

    # Hardcoded base URLs or credentials in spec/page files
    (r"https?://[a-zA-Z0-9._-]+\.(livevox|com|net|io)/", "Hardcoded URL -- import from src/config/ instead"),
    # Credential rule: flag password/secret/token/apikey with a string value >= 4 chars
    # Encrypted values (CryptoJS: U2FsdGVkX1... ending with =) are excluded in _check_line
    (r"(password|secret|token|apikey)\s*[:=]\s*['\"][^'\"]{4,}['\"]", "Possible hardcoded credential -- use config or environment variables"),

    # page.evaluate() with hardcoded JS -- bypasses Playwright auto-retry, fragile
    (r"page\.evaluate\s*\(\s*['\"`]", "page.evaluate() with hardcoded JS string -- use locator actions with auto-retry instead"),
    (r"page\.evaluate\s*\(\s*\(\s*\)\s*=>", "page.evaluate() with inline arrow function -- use Playwright locator actions for auto-retry support"),

    # Deprecated Playwright APIs
    (r"\.\$\s*\(", "Deprecated Playwright API $() detected -- use page.locator() instead"),
    (r"\.\$\$\s*\(", "Deprecated Playwright API $$() detected -- use page.locator() instead"),
    (r"page\.waitForSelector\s*\(", "page.waitForSelector() detected -- use expect(locator).toBeVisible() for auto-retry"),

    # page.waitForNavigation() without Promise.all -- race condition risk
    (r"(?<!Promise\.all\(\[).*page\.waitForNavigation\s*\(", "page.waitForNavigation() without Promise.all -- wrap with Promise.all([page.waitForNavigation(), ...]) to avoid race condition"),

    # beforeAll used for page navigation/login -- shared state across workers is unsafe
    (r"beforeAll\s*\(\s*async\s*\([^)]*page[^)]*\)", "beforeAll() used with page fixture -- use beforeEach() or fixtures to avoid shared state across workers"),

    # Hardcoded locators in spec/test files -- POM violation
    # Locators must live in page objects, not in test files
    (r"page\.locator\s*\(", "page.locator() used in spec file -- POM violation: move locator to page object and expose via a method"),
]

MEDIUM_PATTERNS = [
    # Debug leftovers
    (r"console\.(log|warn|error|info)\s*\(", "console.log left in code -- remove before merging"),
    (r"System\.out\.print", "System.out.println left in code"),

    # waitForTimeout with short values (still discouraged)
    (r"waitForTimeout\s*\(\s*\d{1,3}\s*\)", "waitForTimeout usage -- prefer expect() auto-waiting"),
    (r"waitForTimeout\s*\(\s*\d{3}\s*\)", "waitForTimeout usage -- prefer expect() auto-waiting"),

    # Import from wrong config path (should always be src/config/)
    (r"from\s+['\"]\.\.\/\.\.\/config(?!\/stg4|\/tst2)", "Config import not from src/config/stg4 or src/config/tst2"),

    # Page objects placed outside correct folder
    (r"class\s+\w+Page\s+", "Page class detected -- verify it is placed under src/ui/pages/"),

    # Emojis or non-standard characters in comments (repo standard: no emojis in comments)
    # Non-ASCII in comments -- exclude common section-separator decorators (em-dash, box-drawing)
    (r"//(?!.*[\u2500-\u257F\u2014\u2013]).*[^\x00-\x7F]", "Non-ASCII character in comment -- keep comments plain ASCII"),

    # page.reload() without assertion after -- no verification that reload completed
    (r"await\s+page\.reload\s*\(\s*\)", "page.reload() without follow-up assertion -- add expect() to verify page state after reload"),

    # page.screenshot() left unconditionally -- slows down test runs if always-on
    (r"page\.screenshot\s*\(", "page.screenshot() detected -- ensure this is conditional or inside onTestFailed hook, not always-on"),

    # TypeScript any type in test or page files -- defeats type safety
    (r":\s*any\b", "TypeScript 'any' type detected -- use specific types to maintain type safety"),
    (r"as\s+any\b", "TypeScript 'as any' cast detected -- use proper typing instead"),

    # page passed as parameter between helper functions -- signals missing fixture/POM abstraction
    (r"(function|const)\s+\w+\s*\([^)]*\bpage\s*:\s*Page\b", "page: Page passed as parameter to helper -- consider using a fixture or POM method instead"),

    # Missing await before expect when using async values
    (r"expect\s*\(\s*await\s+page\.(title|url|content|innerText|textContent|inputValue)\s*\(", "await inside expect() -- move await outside: const val = await ...; expect(val)"),
]

LOW_PATTERNS = [
    (r"TODO|FIXME|HACK|XXX", "TODO/FIXME comment -- track in Jira with a ticket reference"),

    # test.only / describe.only should never be committed
    (r"(test|it|describe)\.only\s*\(", "test.only/describe.only committed -- will block other tests from running"),

    # test.setTimeout() inside a test -- override in playwright.config.ts instead
    (r"test\.setTimeout\s*\(", "Insight: test.setTimeout() inside test -- set timeout globally in playwright.config.ts instead"),

    # page.fill() old API -- prefer locator.fill()
    (r"page\.fill\s*\(", "Insight: page.fill(selector, value) is the older API -- prefer locator.fill() for better reliability"),

    # Unnamed describe block
    (r"describe\s*\(\s*['\"]['\"]", "Insight: Empty describe() label -- give suites a meaningful name for report readability"),
    (r"describe\s*\(\s*,", "Insight: describe() called without a label -- add a meaningful suite name"),

    # Missing @tag annotation on tests -- hard to filter in CI
    (r"test\s*\(\s*['\"](?!.*@)", "Insight: Test has no @tag annotation -- consider adding tags (e.g., '@smoke', '@regression') for CI filtering"),

    # Insight: Playwright built-in locator methods detected.
    # Flagged as informational only -- do not block the pipeline.
    (r"\.getByRole\s*\(", "Insight: getByRole() detected -- consider page.locator() with CSS selector per repo locator strategy"),
    (r"\.getByTestId\s*\(", "Insight: getByTestId() detected -- consider page.locator('[data-testid=\"...\"]') directly"),
    (r"\.getByText\s*\(", "Insight: getByText() detected -- consider page.locator() with CSS or XPath"),
    (r"\.getByLabel\s*\(", "Insight: getByLabel() detected -- consider page.locator() with CSS selector"),
    (r"\.getByPlaceholder\s*\(", "Insight: getByPlaceholder() detected -- consider page.locator('[placeholder=\"...\"]')"),
    (r"\.getByAltText\s*\(", "Insight: getByAltText() detected -- consider page.locator() with CSS selector"),
    (r"\.getByTitle\s*\(", "Insight: getByTitle() detected -- consider page.locator() with CSS selector"),
]

# Directories to always skip.
# Includes the agent's own infrastructure (codeReviewScripts, skills, .github)
# so the reviewer never reviews itself -- its regex patterns are string literals
# that would otherwise self-match.
SKIP_DIRS = {
    "node_modules", "dist", "allure-results",
    "playwright-report", "test-results", ".git", ".playwright-mcp",
    "codeReviewScripts", "skills", ".github",
}

# Source file extensions to review.
# Widened beyond Playwright-TS so the deterministic Layer-1 pass runs on any
# supported QA automation stack. Regex rules that do not match a given language
# simply produce no findings; the LLM layer (Layer 2) generalizes semantically.
REVIEW_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs",   # Playwright TS/JS
    ".java",                                  # Selenium / Playwright Java
    ".feature",                               # BDD / Cucumber Gherkin
    ".py", ".cs", ".rb",                      # other automation stacks
}


# ----------------------------------------------------------------------------
# DIFF / FILE ANALYSIS
# ----------------------------------------------------------------------------

def should_skip_file(file_path: str) -> bool:
    """Return True if the file should be excluded from review."""
    parts = file_path.replace("\\", "/").split("/")
    if any(seg in SKIP_DIRS for seg in parts):
        return True
    return Path(file_path).suffix not in REVIEW_EXTENSIONS


def _file_level_findings(file_path: str) -> list:
    """Checks that apply once per file rather than per line."""
    findings = []
    name = Path(file_path).name
    # Test files must follow the .spec.ts naming convention so Playwright discovers them
    if (
        "tests/" in file_path or "test/" in file_path
    ) and name.endswith(".ts") and not name.endswith(".spec.ts"):
        findings.append({
            "severity": "High",
            "file": file_path,
            "line": 1,
            "rule": "Test file does not follow .spec.ts naming -- Playwright test runner may not discover it",
            "code": name,
        })
    return findings


def _check_line(code: str, file_path: str, line_number: int, is_page_object: bool) -> list:
    """Run all pattern checks against a single line of code."""
    findings = []
    is_spec_file = file_path.endswith(".spec.ts") or file_path.endswith(".spec.js")

    for pattern, rule_name in CRITICAL_PATTERNS:
        # Nested test() check only makes sense inside spec files
        if "Nested test()" in rule_name and not is_spec_file:
            continue
        # Playwright test import check only applies to page object files
        if "Page Objects must only import" in rule_name and not is_page_object:
            continue
        if "without Page type" in rule_name and not is_page_object:
            continue
        if re.search(pattern, code, re.IGNORECASE):
            # Skip unawaited-action rule if 'await' appears anywhere on the line
            if "missing await" in rule_name and "await" in code:
                continue
            # Skip C8 if Page or Locator is also imported (legitimate usage)
            if "without Page type" in rule_name and re.search(r"\b(Page|Locator)\b", code):
                continue
            # Downgrade waitForTimeout from Critical to Medium in page objects
            # (used as UI stabilization waits; still Critical in spec/test files)
            if "waitForTimeout" in rule_name and is_page_object:
                findings.append({"severity": "Medium", "file": file_path, "line": line_number, "rule": rule_name + " (consider replacing with locator.waitFor())", "code": code.strip()[:120]})
            else:
                findings.append({"severity": "Critical", "file": file_path, "line": line_number, "rule": rule_name, "code": code.strip()[:120]})

    for pattern, rule_name in HIGH_PATTERNS:
        if "Value assertion found" in rule_name and not is_page_object:
            continue
        # page.locator() POM violation only applies to spec/test files
        if "page.locator() used in spec file" in rule_name and not is_spec_file:
            continue
        if re.search(pattern, code, re.IGNORECASE):
            # Skip credential rule if value is CryptoJS encrypted (starts with U2FsdGVkX1 and ends with =)
            if "hardcoded credential" in rule_name and re.search(r"['\"]U2FsdGVkX1[A-Za-z0-9+/]+=*['\"]", code):
                continue
            findings.append({"severity": "High", "file": file_path, "line": line_number, "rule": rule_name, "code": code.strip()[:120]})

    for pattern, rule_name in MEDIUM_PATTERNS:
        # M4: skip Page class placement check if already in the correct folder
        if "Page class detected" in rule_name and "src/ui/pages/" in file_path:
            continue
        if re.search(pattern, code, re.IGNORECASE):
            findings.append({"severity": "Medium", "file": file_path, "line": line_number, "rule": rule_name, "code": code.strip()[:120]})

    for pattern, rule_name in LOW_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            findings.append({"severity": "Low", "file": file_path, "line": line_number, "rule": rule_name, "code": code.strip()[:120]})

    return findings


def analyze_diff(diff_text: str, file_path: str) -> list:
    """Analyze a unified diff (added lines only) and return findings."""
    findings = _file_level_findings(file_path)
    is_page_object = "pages/" in file_path or "page-objects/" in file_path
    current_line = 0

    for line in diff_text.split("\n"):
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", line)
        if hunk_match:
            current_line = int(hunk_match.group(1)) - 1
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_line += 1
            findings.extend(_check_line(line[1:], file_path, current_line, is_page_object))
        elif not line.startswith("-"):
            current_line += 1

    return findings


def analyze_file_content(content: str, file_path: str) -> list:
    """Analyze all lines of a full file and return findings."""
    is_page_object = "pages/" in file_path or "page-objects/" in file_path
    is_spec_file = file_path.endswith(".spec.ts") or file_path.endswith(".spec.js")
    findings = _file_level_findings(file_path)

    # Context-aware nested test() detection:
    # A test() is nested only when it appears INSIDE another test() callback body,
    # not simply inside a test.describe() block (which is valid Playwright structure).
    inside_test_body = False
    test_brace_depth = 0
    brace_depth = 0

    for line_number, raw_line in enumerate(content.split("\n"), start=1):
        findings.extend(_check_line(raw_line, file_path, line_number, is_page_object))

        if is_spec_file:
            stripped = raw_line.strip()
            # Detect entry into a test() callback (but not test.describe)
            if re.search(r"\btest\s*\(", stripped) and not re.search(r"\btest\.(describe|beforeAll|beforeEach|afterAll|afterEach|skip|only)\s*\(", stripped):
                if not inside_test_body:
                    inside_test_body = True
                    test_brace_depth = brace_depth
                else:
                    # We are already inside a test() body -- this is a genuinely nested test()
                    findings.append({
                        "severity": "Critical",
                        "file": file_path,
                        "line": line_number,
                        "rule": "Nested test() detected -- Playwright does not support tests nested inside other tests",
                        "code": raw_line.strip()[:120],
                    })

            brace_depth += stripped.count("{") - stripped.count("}")
            if inside_test_body and brace_depth <= test_brace_depth:
                inside_test_body = False
                test_brace_depth = 0

    return findings


# ----------------------------------------------------------------------------
# SCORING & REPORTING
# ----------------------------------------------------------------------------

def compute_score(findings: list) -> tuple:
    score = 100
    for f in findings:
        if f["severity"] == "Critical":
            score -= 15
        elif f["severity"] == "High":
            score -= 7
        elif f["severity"] == "Medium":
            score -= 3
        elif f["severity"] == "Low":
            score -= 1
    score = max(0, score)

    if score >= 90:
        verdict = "Approve"
    elif score >= 75:
        verdict = "Approve with comments"
    elif score >= 50:
        verdict = "Request changes"
    else:
        verdict = "Block"

    return score, verdict


def format_report(findings: list, score: int, verdict: str, context_info: dict) -> str:
    critical = [f for f in findings if f["severity"] == "Critical"]
    high     = [f for f in findings if f["severity"] == "High"]
    medium   = [f for f in findings if f["severity"] == "Medium"]
    low      = [f for f in findings if f["severity"] == "Low"]

    mode_label = context_info.get("mode_label", "")
    report = f"""## QA Automation Code Review{(' -- ' + mode_label) if mode_label else ''}

**Health Score: {score}/100 -- {verdict}**

| Severity | Count |
|----------|-------|
| Critical | {len(critical)} |
| High     | {len(high)} |
| Medium   | {len(medium)} |
| Low      | {len(low)} |

"""

    if not findings:
        report += "### No issues found -- great job!\n"
        return report

    def render_section(label, items, collapsed=False):
        if not items:
            return ""
        out = ""
        if collapsed:
            out += f"<details><summary>{label} ({len(items)} items)</summary>\n\n"
        else:
            out += f"### {label}\n\n"
        for f in items:
            out += f"- **`{f['file']}:{f['line']}`** -- {f['rule']}\n"
            out += f"  ```\n  {f['code']}\n  ```\n"
        if collapsed:
            out += "\n</details>\n"
        out += "\n"
        return out

    report += render_section("Critical", critical)
    report += render_section("High", high)
    report += render_section("Medium", medium)
    report += render_section("Low", low, collapsed=True)
    report += "\n---\n*Automated review by QA Code Review Agent*\n"
    return report


def save_and_print_report(report: str, findings: list, score: int, verdict: str):
    with open("review_report.md", "w") as f:
        f.write(report)
    print("review_report.md saved")

    critical_count = len([f for f in findings if f["severity"] == "Critical"])
    high_count     = len([f for f in findings if f["severity"] == "High"])

    if critical_count > 0 or high_count > 0:
        print(f"Pipeline FAILED -- {critical_count} Critical, {high_count} High findings must be resolved.")
        sys.exit(1)
    elif score >= 80:
        print(f"Pipeline PASSED -- No Critical/High findings. Health score: {score}/100.")
    else:
        print(f"Pipeline PASSED with warnings -- Health score: {score}/100 (below 80).")


# ----------------------------------------------------------------------------
# API HELPERS
# ----------------------------------------------------------------------------

def gitlab_api(method: str, endpoint: str, data: Optional[dict] = None) -> dict:
    api_url = os.environ["GITLAB_API_URL"]
    token   = os.environ["GITLAB_PERSONAL_ACCESS_TOKEN"]
    url     = f"{api_url}{endpoint}"
    headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    body    = json.dumps(data).encode() if data else None
    req     = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"GitLab API error: {e.code} {e.read().decode()[:500]}")
        raise


def github_api(method: str, endpoint: str, data: Optional[dict] = None) -> dict:
    token   = os.environ["GITHUB_TOKEN"]
    url     = f"https://api.github.com{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e.code} {e.read().decode()[:500]}")
        raise


# ----------------------------------------------------------------------------
# MODE 1 -- PR / MR  (automatic on CI events)
# ----------------------------------------------------------------------------

def run_gitlab_pr_review():
    project_id = os.environ["CI_PROJECT_ID"]
    mr_iid     = os.environ["CI_MERGE_REQUEST_IID"]
    print(f"[Mode: PR/MR] Reviewing GitLab MR !{mr_iid} in project {project_id}")

    mr      = gitlab_api("GET", f"/projects/{project_id}/merge_requests/{mr_iid}")
    changes = gitlab_api("GET", f"/projects/{project_id}/merge_requests/{mr_iid}/changes")
    diffs   = changes.get("changes", [])
    print(f"Files in MR diff: {len(diffs)}")

    all_findings = []
    for diff_item in diffs:
        file_path = diff_item.get("new_path", diff_item.get("old_path", "unknown"))
        if should_skip_file(file_path):
            continue
        print(f"  Checking: {file_path}")
        all_findings.extend(analyze_diff(diff_item.get("diff", ""), file_path))

    score, verdict = compute_score(all_findings)
    report = format_report(all_findings, score, verdict, {"mode_label": f"MR !{mr_iid}"})
    print(f"\nScore: {score}/100 -- {verdict} | Findings: {len(all_findings)}")
    gitlab_api("POST", f"/projects/{project_id}/merge_requests/{mr_iid}/notes", {"body": report})
    print(f"Review comment posted on MR !{mr_iid}")
    save_and_print_report(report, all_findings, score, verdict)


def run_github_pr_review():
    repo      = os.environ["GITHUB_REPOSITORY"]
    pr_number = os.environ["PR_NUMBER"]
    print(f"[Mode: PR/MR] Reviewing GitHub PR #{pr_number} in {repo}")

    files = github_api("GET", f"/repos/{repo}/pulls/{pr_number}/files")
    print(f"Files in PR diff: {len(files)}")

    all_findings = []
    for file_item in files:
        file_path = file_item.get("filename", "")
        if should_skip_file(file_path):
            continue
        print(f"  Checking: {file_path}")
        diff_text = file_item.get("patch", "")
        if diff_text:
            all_findings.extend(analyze_diff(diff_text, file_path))

    score, verdict = compute_score(all_findings)
    report = format_report(all_findings, score, verdict, {"mode_label": f"PR #{pr_number}"})
    print(f"\nScore: {score}/100 -- {verdict} | Findings: {len(all_findings)}")
    github_api("POST", f"/repos/{repo}/issues/{pr_number}/comments", {"body": report})
    print(f"Review comment posted on PR #{pr_number}")
    save_and_print_report(report, all_findings, score, verdict)


# ----------------------------------------------------------------------------
# MODE 2 -- COMMIT  (review a specific commit by SHA)
# ----------------------------------------------------------------------------

def run_gitlab_commit_review():
    project_id = os.environ["CI_PROJECT_ID"]
    commit_sha = os.environ["COMMIT_SHA"].strip()
    print(f"[Mode: Commit] Reviewing GitLab commit {commit_sha[:8]} in project {project_id}")

    diffs = gitlab_api("GET", f"/projects/{project_id}/repository/commits/{commit_sha}/diff")
    print(f"Files in commit diff: {len(diffs)}")

    all_findings = []
    for diff_item in diffs:
        file_path = diff_item.get("new_path", diff_item.get("old_path", "unknown"))
        if should_skip_file(file_path):
            continue
        print(f"  Checking: {file_path}")
        all_findings.extend(analyze_diff(diff_item.get("diff", ""), file_path))

    score, verdict = compute_score(all_findings)
    report = format_report(all_findings, score, verdict, {"mode_label": f"Commit {commit_sha[:8]}"})
    print(f"\nScore: {score}/100 -- {verdict} | Findings: {len(all_findings)}")
    gitlab_api(
        "POST",
        f"/projects/{project_id}/repository/commits/{commit_sha}/comments",
        {"note": report},
    )
    print(f"Review comment posted on commit {commit_sha[:8]}")
    save_and_print_report(report, all_findings, score, verdict)


def run_github_commit_review():
    repo       = os.environ["GITHUB_REPOSITORY"]
    commit_sha = os.environ["COMMIT_SHA"].strip()
    print(f"[Mode: Commit] Reviewing GitHub commit {commit_sha[:8]} in {repo}")

    commit_data = github_api("GET", f"/repos/{repo}/commits/{commit_sha}")
    files       = commit_data.get("files", [])
    print(f"Files in commit diff: {len(files)}")

    all_findings = []
    for file_item in files:
        file_path = file_item.get("filename", "")
        if should_skip_file(file_path):
            continue
        print(f"  Checking: {file_path}")
        diff_text = file_item.get("patch", "")
        if diff_text:
            all_findings.extend(analyze_diff(diff_text, file_path))

    score, verdict = compute_score(all_findings)
    report = format_report(all_findings, score, verdict, {"mode_label": f"Commit {commit_sha[:8]}"})
    print(f"\nScore: {score}/100 -- {verdict} | Findings: {len(all_findings)}")
    github_api(
        "POST",
        f"/repos/{repo}/commits/{commit_sha}/comments",
        {"body": report},
    )
    print(f"Review comment posted on commit {commit_sha[:8]}")
    save_and_print_report(report, all_findings, score, verdict)


# ----------------------------------------------------------------------------
# MODE 3 -- REPO  (scan entire repository on disk)
# ----------------------------------------------------------------------------

def run_repo_review(post_comment: bool = False):
    repo_root = Path(os.environ.get("REPO_ROOT", ".")).resolve()
    print(f"[Mode: Repo] Scanning full repository at: {repo_root}")

    all_findings = []
    scanned = 0

    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
        if should_skip_file(rel_path):
            continue
        print(f"  Checking: {rel_path}")
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"  Could not read {rel_path}: {e}")
            continue
        all_findings.extend(analyze_file_content(content, rel_path))
        scanned += 1

    print(f"\nScanned {scanned} file(s)")
    score, verdict = compute_score(all_findings)
    report = format_report(all_findings, score, verdict, {"mode_label": f"Full Repo ({scanned} files)"})
    print(f"Score: {score}/100 -- {verdict} | Findings: {len(all_findings)}")

    save_and_print_report(report, all_findings, score, verdict)


# ----------------------------------------------------------------------------
# CI SOURCE DETECTION
# ----------------------------------------------------------------------------

def detect_ci_source() -> str:
    if os.environ.get("GITLAB_CI"):
        return "gitlab"
    elif os.environ.get("GITHUB_ACTIONS"):
        return "github"
    return os.environ.get("CI_SOURCE", "unknown")


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    source      = detect_ci_source()
    review_mode = os.environ.get("REVIEW_MODE", "pr").lower().strip()

    print("QA Automation Code Review Agent")
    print(f"  CI Source   : {source}")
    print(f"  Review Mode : {review_mode}")
    print("-" * 50)

    # Mode: repo -- scan entire repository on disk
    if review_mode == "repo":
        post = bool(os.environ.get("CI_MERGE_REQUEST_IID") or os.environ.get("PR_NUMBER"))
        run_repo_review(post_comment=post)

    # Mode: commit -- review a single commit by SHA
    elif review_mode == "commit":
        if not os.environ.get("COMMIT_SHA", "").strip():
            print("ERROR: COMMIT_SHA environment variable is required for commit mode.")
            sys.exit(1)
        if source == "gitlab":
            run_gitlab_commit_review()
        elif source == "github":
            run_github_commit_review()
        else:
            print("ERROR: Unknown CI source. Set CI_SOURCE=gitlab or CI_SOURCE=github")
            sys.exit(1)

    # Mode: pr (default) -- review the open PR/MR diff
    else:
        if source == "gitlab":
            run_gitlab_pr_review()
        elif source == "github":
            run_github_pr_review()
        else:
            print("ERROR: Unknown CI source. Set CI_SOURCE=gitlab or CI_SOURCE=github")
            sys.exit(1)
