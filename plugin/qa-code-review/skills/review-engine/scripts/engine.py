#!/usr/bin/env python3
"""
QA Automation Code Review -- deterministic engine (Layer 1 only, NO LLM).

Review is 100% script + SKILL.md driven: this module loads each active
skill's `scripts/review.py` (as resolved by `detect_framework.py`) and runs
its patterns against the file(s) under review. There is no LLM involved in
finding issues -- only in `llm_fix.py`, which fixes what this engine reports.

Supports three review modes, selected via the REVIEW_MODE environment
variable:
  REVIEW_MODE=pr      -- PR (GitHub) or MR (GitLab) diff/full-content review
  REVIEW_MODE=commit  -- review a single specific commit by SHA
  REVIEW_MODE=repo    -- scan every matching source file in the working tree
  REVIEW_MODE=local   -- review the repo's currently staged + unstaged changes
                         (git diff --cached + git diff); use this for a local,
                         not-yet-pushed review of specific files

CI_SOURCE ("github" | "gitlab") is auto-detected from the environment for the
pr/commit modes; PR posting/fetching and MR posting/fetching are both
supported so the same engine works unmodified on either platform.
"""

import importlib.util
import os
import re
import subprocess
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect_framework as dispatcher  # noqa: E402


# ----------------------------------------------------------------------------
# SKILL PATTERN LOADING
# ----------------------------------------------------------------------------

def _load_skill_module(skills_dir: Path, skill_name: str):
    """Dynamically import <skills_dir>/<skill_name>/scripts/review.py, if present."""
    mod_path = skills_dir / skill_name / "scripts" / "review.py"
    if not mod_path.is_file():
        return None
    mod_name = f"qa_skill_review__{skill_name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(mod_name, mod_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def load_patterns(skill_names: List[str], skills_dir: Optional[str] = None) -> dict:
    """Merge CRITICAL/HIGH/MEDIUM/LOW pattern lists from every active skill.

    Order matters for readability of the report only (qa-review-core first,
    driver overlay next, bdd-cucumber last) -- scoring does not depend on it.
    Also captures the bdd-cucumber FEATURE_*/STEP_* sets separately, if present.
    """
    base = Path(skills_dir) if skills_dir else dispatcher.plugin_skills_dir()
    merged = {"critical": [], "high": [], "medium": [], "low": [],
              "feature_high": [], "feature_medium": [], "feature_low": [],
              "step_high": [], "step_medium": [], "step_low": []}
    for name in skill_names:
        mod = _load_skill_module(base, name)
        if mod is None:
            print(f"  [engine] WARNING: no scripts/review.py for skill '{name}' at {base / name}")
            continue
        merged["critical"].extend(getattr(mod, "CRITICAL_PATTERNS", []))
        merged["high"].extend(getattr(mod, "HIGH_PATTERNS", []))
        merged["medium"].extend(getattr(mod, "MEDIUM_PATTERNS", []))
        merged["low"].extend(getattr(mod, "LOW_PATTERNS", []))
        merged["feature_high"].extend(getattr(mod, "FEATURE_HIGH_PATTERNS", []))
        merged["feature_medium"].extend(getattr(mod, "FEATURE_MEDIUM_PATTERNS", []))
        merged["feature_low"].extend(getattr(mod, "FEATURE_LOW_PATTERNS", []))
        merged["step_high"].extend(getattr(mod, "STEP_HIGH_PATTERNS", []))
        merged["step_medium"].extend(getattr(mod, "STEP_MEDIUM_PATTERNS", []))
        merged["step_low"].extend(getattr(mod, "STEP_LOW_PATTERNS", []))
    return merged


# ----------------------------------------------------------------------------
# FILE FILTERING
# ----------------------------------------------------------------------------

SKIP_DIRS = {
    "node_modules", "dist", "allure-results",
    "playwright-report", "test-results", ".git", ".playwright-mcp",
    "skills", ".github", "target", "build",
}

REVIEW_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs",   # Playwright TS/JS
    ".java",                                 # Selenium / Playwright Java
    ".feature",                              # BDD / Cucumber Gherkin
    ".py", ".cs", ".rb",                     # other automation stacks
}


def should_skip_file(file_path: str) -> bool:
    parts = file_path.replace("\\", "/").split("/")
    if any(seg in SKIP_DIRS for seg in parts):
        return True
    return Path(file_path).suffix not in REVIEW_EXTENSIONS


def _is_step_definition_file(file_path: str) -> bool:
    lower = file_path.replace("\\", "/").lower()
    return "step_definitions" in lower or "/steps/" in lower or lower.endswith("steps.java") \
        or lower.endswith("stepdefs.java") or lower.endswith("steps.ts") or lower.endswith("steps.js")


# ----------------------------------------------------------------------------
# LINE / DIFF / FULL-FILE ANALYSIS
# ----------------------------------------------------------------------------

def _file_level_findings(file_path: str) -> list:
    """Checks that apply once per file rather than per line."""
    findings = []
    name = Path(file_path).name
    if ("tests/" in file_path or "test/" in file_path) and name.endswith(".ts") and not name.endswith(".spec.ts"):
        findings.append({
            "severity": "High", "file": file_path, "line": 1,
            "rule": "Test file does not follow .spec.ts naming -- Playwright test runner may not discover it",
            "code": name,
        })
    return findings


def _check_line(code: str, file_path: str, line_number: int, is_page_object: bool, patterns: dict) -> list:
    """Run all merged pattern checks against a single line of code."""
    findings = []
    is_spec_file = file_path.endswith(".spec.ts") or file_path.endswith(".spec.js")
    is_feature = file_path.endswith(".feature")

    critical = patterns["critical"]
    high = patterns["high"] + (patterns["feature_high"] if is_feature else []) \
        + (patterns["step_high"] if _is_step_definition_file(file_path) else [])
    medium = patterns["medium"] + (patterns["feature_medium"] if is_feature else []) \
        + (patterns["step_medium"] if _is_step_definition_file(file_path) else [])
    low = patterns["low"] + (patterns["feature_low"] if is_feature else []) \
        + (patterns["step_low"] if _is_step_definition_file(file_path) else [])

    for pattern, rule_name in critical:
        if "without Page type" in rule_name and not is_page_object:
            continue
        if re.search(pattern, code, re.IGNORECASE):
            if "missing await" in rule_name and "await" in code:
                continue
            if "without Page type" in rule_name and re.search(r"\b(Page|Locator)\b", code):
                continue
            if "waitForTimeout" in rule_name and is_page_object:
                findings.append({"severity": "Medium", "file": file_path, "line": line_number,
                                  "rule": rule_name + " (consider replacing with locator.waitFor())",
                                  "code": code.strip()[:120]})
            else:
                findings.append({"severity": "Critical", "file": file_path, "line": line_number,
                                  "rule": rule_name, "code": code.strip()[:120]})

    for pattern, rule_name in high:
        if "Value assertion found" in rule_name and not is_page_object:
            continue
        if "Assertion found in Page Object" in rule_name and not is_page_object:
            continue
        if "page.locator() used in spec file" in rule_name and not is_spec_file:
            continue
        if "without Page type" in rule_name and not is_page_object:
            continue
        if re.search(pattern, code, re.IGNORECASE):
            if "hardcoded credential" in rule_name and re.search(r"['\"]U2FsdGVkX1[A-Za-z0-9+/]+=*['\"]", code):
                continue
            if "without Page type" in rule_name and re.search(r"\b(Page|Locator)\b", code):
                continue
            findings.append({"severity": "High", "file": file_path, "line": line_number,
                              "rule": rule_name, "code": code.strip()[:120]})

    for pattern, rule_name in medium:
        if "Page class detected" in rule_name and "pages/" in file_path:
            continue
        if re.search(pattern, code, re.IGNORECASE):
            findings.append({"severity": "Medium", "file": file_path, "line": line_number,
                              "rule": rule_name, "code": code.strip()[:120]})

    for pattern, rule_name in low:
        if re.search(pattern, code, re.IGNORECASE):
            findings.append({"severity": "Low", "file": file_path, "line": line_number,
                              "rule": rule_name, "code": code.strip()[:120]})

    return findings


def analyze_diff(diff_text: str, file_path: str, patterns: dict) -> list:
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
            findings.extend(_check_line(line[1:], file_path, current_line, is_page_object, patterns))
        elif not line.startswith("-"):
            current_line += 1

    return findings


def analyze_file_content(content: str, file_path: str, patterns: dict) -> list:
    """Analyze all lines of a full file and return findings."""
    is_page_object = "pages/" in file_path or "page-objects/" in file_path
    is_spec_file = file_path.endswith(".spec.ts") or file_path.endswith(".spec.js")
    findings = _file_level_findings(file_path)

    inside_test_body = False
    test_brace_depth = 0
    brace_depth = 0

    for line_number, raw_line in enumerate(content.split("\n"), start=1):
        findings.extend(_check_line(raw_line, file_path, line_number, is_page_object, patterns))

        if is_spec_file:
            stripped = raw_line.strip()
            if re.search(r"\btest\s*\(", stripped) and not re.search(r"\btest\.(describe|beforeAll|beforeEach|afterAll|afterEach|skip|only)\s*\(", stripped):
                if not inside_test_body:
                    inside_test_body = True
                    test_brace_depth = brace_depth
                else:
                    findings.append({
                        "severity": "Critical", "file": file_path, "line": line_number,
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
    skills_label = context_info.get("skills_label", "")
    skills_line = f"  \n_Skills applied: {skills_label}_" if skills_label else ""
    report = f"""## QA Automation Code Review{(' -- ' + mode_label) if mode_label else ''}

**Health Score: {score}/100 -- {verdict}**{skills_line}

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
    report += "\n---\n*Deterministic review by QA Code Review Agent -- script + SKILL.md only, no LLM involved in findings*\n"
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
# RETRY HELPER (transient network/push failures -- PR-level resilience)
# ----------------------------------------------------------------------------

def with_retries(fn, *args, max_retries: int = 3, label: str = "operation", **kwargs):
    """Retry a callable up to max_retries times on exception. Re-raises the
    last exception if every attempt fails. Used for network calls (GitHub/
    GitLab API) where a transient failure should not abort the whole review."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - genuinely retry-anything here
            last_exc = exc
            print(f"  [retry] {label} failed (attempt {attempt}/{max_retries}): {exc}")
    raise last_exc


# ----------------------------------------------------------------------------
# API HELPERS -- GitHub + GitLab
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


def detect_ci_source() -> str:
    if os.environ.get("GITLAB_CI"):
        return "gitlab"
    elif os.environ.get("GITHUB_ACTIONS"):
        return "github"
    return os.environ.get("CI_SOURCE", "unknown")


# ----------------------------------------------------------------------------
# MODE: repo -- scan entire repository on disk
# ----------------------------------------------------------------------------

def run_repo_review():
    repo_root = Path(os.environ.get("REPO_ROOT", ".")).resolve()
    print(f"[Mode: Repo] Scanning full repository at: {repo_root}")

    resolved = dispatcher.resolve(str(repo_root))
    patterns = load_patterns(resolved["skills"], os.environ.get("SKILLS_DIR"))
    print(f"Skills applied: {', '.join(resolved['skills'])}")

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
        all_findings.extend(analyze_file_content(content, rel_path, patterns))
        scanned += 1

    print(f"\nScanned {scanned} file(s)")
    score, verdict = compute_score(all_findings)
    report = format_report(all_findings, score, verdict,
                            {"mode_label": f"Full Repo ({scanned} files)",
                             "skills_label": ", ".join(resolved["skills"])})
    print(f"Score: {score}/100 -- {verdict} | Findings: {len(all_findings)}")
    save_and_print_report(report, all_findings, score, verdict)


# ----------------------------------------------------------------------------
# MODE: local -- staged + unstaged working-tree changes
# ----------------------------------------------------------------------------

def _git(cmd: List[str], cwd: str) -> str:
    res = subprocess.run(["git"] + cmd, cwd=cwd, capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else ""


def run_local_review():
    """Review the CURRENT full content of every file with staged or unstaged
    changes. Reading full content (not `git diff`) means a file that is fully
    staged with no unstaged delta -- where a plain `git diff` returns nothing
    -- is still reviewed correctly."""
    repo_root = os.environ.get("REPO_ROOT", ".")
    print(f"[Mode: Local] Reviewing staged + unstaged changes in: {repo_root}")

    resolved = dispatcher.resolve(repo_root)
    patterns = load_patterns(resolved["skills"], os.environ.get("SKILLS_DIR"))
    print(f"Skills applied: {', '.join(resolved['skills'])}")

    staged = _git(["diff", "--cached", "--name-only"], repo_root).splitlines()
    unstaged = _git(["diff", "--name-only"], repo_root).splitlines()
    untracked = _git(["ls-files", "--others", "--exclude-standard"], repo_root).splitlines()
    changed = sorted(set(staged) | set(unstaged) | set(untracked))
    changed = [f for f in changed if not should_skip_file(f)]
    print(f"Changed files: {len(changed)}")

    all_findings = []
    for rel in changed:
        fp = Path(repo_root) / rel
        if not fp.is_file():
            continue
        print(f"  Checking: {rel}")
        content = fp.read_text(encoding="utf-8", errors="ignore")
        all_findings.extend(analyze_file_content(content, rel, patterns))

    score, verdict = compute_score(all_findings)
    report = format_report(all_findings, score, verdict,
                            {"mode_label": f"Local ({len(changed)} changed files)",
                             "skills_label": ", ".join(resolved["skills"])})
    print(f"Score: {score}/100 -- {verdict} | Findings: {len(all_findings)}")
    save_and_print_report(report, all_findings, score, verdict)


# ----------------------------------------------------------------------------
# MODE: commit -- review a single commit by SHA (GitHub or GitLab)
# ----------------------------------------------------------------------------

def run_commit_review():
    source = detect_ci_source()
    commit_sha = os.environ["COMMIT_SHA"].strip()
    repo_root = os.environ.get("REPO_ROOT", ".")
    resolved = dispatcher.resolve(repo_root)
    patterns = load_patterns(resolved["skills"], os.environ.get("SKILLS_DIR"))

    if source == "gitlab":
        project_id = os.environ["CI_PROJECT_ID"]
        print(f"[Mode: Commit] Reviewing GitLab commit {commit_sha[:8]} in project {project_id}")
        diffs = with_retries(gitlab_api, "GET", f"/projects/{project_id}/repository/commits/{commit_sha}/diff", label="GitLab commit diff fetch")
        get_path = lambda d: d.get("new_path", d.get("old_path", "unknown"))
        get_diff = lambda d: d.get("diff", "")
    elif source == "github":
        repo = os.environ["GITHUB_REPOSITORY"]
        print(f"[Mode: Commit] Reviewing GitHub commit {commit_sha[:8]} in {repo}")
        commit_data = with_retries(github_api, "GET", f"/repos/{repo}/commits/{commit_sha}", label="GitHub commit fetch")
        diffs = commit_data.get("files", [])
        get_path = lambda d: d.get("filename", "")
        get_diff = lambda d: d.get("patch", "")
    else:
        print("ERROR: Unknown CI source. Set CI_SOURCE=gitlab or CI_SOURCE=github")
        sys.exit(1)

    print(f"Files in commit diff: {len(diffs)}")
    all_findings = []
    for diff_item in diffs:
        file_path = get_path(diff_item)
        if should_skip_file(file_path):
            continue
        print(f"  Checking: {file_path}")
        all_findings.extend(analyze_diff(get_diff(diff_item), file_path, patterns))

    score, verdict = compute_score(all_findings)
    report = format_report(all_findings, score, verdict,
                            {"mode_label": f"Commit {commit_sha[:8]}",
                             "skills_label": ", ".join(resolved["skills"])})
    print(f"\nScore: {score}/100 -- {verdict} | Findings: {len(all_findings)}")

    if source == "gitlab":
        with_retries(gitlab_api, "POST", f"/projects/{os.environ['CI_PROJECT_ID']}/repository/commits/{commit_sha}/comments",
                     {"note": report}, label="GitLab commit comment post")
    else:
        with_retries(github_api, "POST", f"/repos/{os.environ['GITHUB_REPOSITORY']}/commits/{commit_sha}/comments",
                     {"body": report}, label="GitHub commit comment post")
    print(f"Review comment posted on commit {commit_sha[:8]}")
    save_and_print_report(report, all_findings, score, verdict)


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    review_mode = os.environ.get("REVIEW_MODE", "repo").lower().strip()
    print("QA Automation Code Review Engine (deterministic, no LLM)")
    print(f"  Review Mode : {review_mode}")
    print("-" * 50)

    if review_mode == "repo":
        run_repo_review()
    elif review_mode == "local":
        run_local_review()
    elif review_mode == "commit":
        if not os.environ.get("COMMIT_SHA", "").strip():
            print("ERROR: COMMIT_SHA environment variable is required for commit mode.")
            sys.exit(1)
        run_commit_review()
    else:
        print(f"ERROR: Unsupported REVIEW_MODE '{review_mode}' for engine.py standalone use. "
              "Use pr_review.py for the full PR/MR review + auto-fix loop.")
        sys.exit(1)
