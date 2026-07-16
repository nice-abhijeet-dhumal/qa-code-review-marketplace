#!/usr/bin/env python3
"""
Agentic QA Code Review -- PR/MR orchestrator (GitHub AND GitLab).

Flow (rule: review is script + SKILL.md only, LLM is fix-only):

  1. Detect framework(s) via detect_framework.py -> composed skill list
     (qa-review-core always + one driver overlay + bdd-cucumber if applicable).
  2. Review the CURRENT full content of the changed files using ONLY each
     active skill's scripts/review.py (deterministic_review.py, deterministic --
     no LLM call here at all). Post ONE comment with the findings.
  3. If AUTO_FIX and score < SCORE_THRESHOLD and iteration < MAX_FIX_ITERATIONS
     (PR-level retry cap, default 3): ask the LLM to fix (llm_auto_fix.py) ->
     verify-before-commit gate (re-run deterministic_review.py on the
     candidate, accept only if it does not regress Critical/High) -> commit
     as bot -> push (retried up to 3x on transient failure) -> re-review.
     This runs every time regardless of who authored the PR/MR head -- even
     if the bot's own previous commit is HEAD -- so the pipeline always goes
     review -> findings -> comment -> LLM fix -> re-review, up to the
     MAX_FIX_ITERATIONS cap, on every trigger.

Works on GitHub (PR) and GitLab (MR) via the same entrypoint -- the CI
platform is auto-detected (GITHUB_ACTIONS / GITLAB_CI / CI_SOURCE) and the
right API calls are used for fetching changed files, the source/head branch,
and posting the comment.

Environment:
  Common:
    REPO_ROOT              checkout path (default '.')
    LLM_PROVIDER            claude | github | none (default: auto-detect from
                             ANTHROPIC_API_KEY / GH_MODELS_TOKEN, see llm_client)
    AUTO_FIX                true | false (default false)
    MAX_FIX_ITERATIONS      PR-level retry cap, default 3
    SCORE_THRESHOLD         stop fixing once score >= this, default 80
    BOT_NAME / BOT_EMAIL    fix-commit identity
    API_MAX_RETRIES         retries for transient API calls, default 3

  GitHub:
    GITHUB_TOKEN, GITHUB_REPOSITORY (owner/repo), PR_NUMBER

  GitLab:
    GITLAB_API_URL, GITLAB_PERSONAL_ACCESS_TOKEN, CI_PROJECT_ID,
    CI_MERGE_REQUEST_IID
"""

import os
import sys

from pathlib import Path
from typing import Optional

import deterministic_review
import detect_framework as dispatcher
import llm_auto_fix
from llm_client import choose_provider


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower().strip() in ("1", "true", "yes")


def apply_fixes_gated(fixes: list, repo_root: str, patterns: dict) -> list:
    """Write a candidate fix only if it does NOT regress the file.

    Verify-before-commit: recompute deterministic findings
    (deterministic_review.py) on the candidate content. Accept only if
    Critical/High strictly drops, or holds while total drops. Guarantees the
    deterministic count is monotonically non-increasing across iterations.
    """
    accepted = []
    for fix in fixes:
        rel, content = fix.get("file"), fix.get("content")
        if not rel or content is None:
            continue
        target = Path(repo_root) / rel
        if not target.is_file():
            continue
        old = target.read_text(encoding="utf-8", errors="ignore")
        if old == content:
            continue
        old_f = deterministic_review.analyze_file_content(old, rel, patterns)
        new_f = deterministic_review.analyze_file_content(content, rel, patterns)
        old_ch, new_ch = _critical_high(old_f), _critical_high(new_f)
        improves = new_ch < old_ch or (new_ch == old_ch and len(new_f) < len(old_f))
        if not improves:
            print(f"  [gate] REJECTED fix for {rel}: no improvement "
                  f"(Critical/High {old_ch}->{new_ch}, total {len(old_f)}->{len(new_f)})")
            continue
        target.write_text(content, encoding="utf-8")
        print(f"  [gate] accepted fix for {rel}: "
              f"Critical/High {old_ch}->{new_ch}, total {len(old_f)}->{len(new_f)}")
        accepted.append(rel)
    return accepted


def _read(repo_root: str, path: str) -> Optional[str]:
    fp = Path(repo_root) / path
    if not fp.is_file():
        return None
    return fp.read_text(encoding="utf-8", errors="ignore")


def _critical_high(findings: list) -> int:
    return sum(1 for f in findings if f["severity"] in ("Critical", "High"))


# ----------------------------------------------------------------------------
# Platform adapters -- GitHub PR / GitLab MR
# ----------------------------------------------------------------------------

class GitHubAdapter:
    label = "PR"

    def __init__(self, retries: int):
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.number = os.environ["PR_NUMBER"]
        self.retries = retries

    def changed_files(self) -> list:
        files = deterministic_review.with_retries(
            deterministic_review.github_api, "GET", f"/repos/{self.repo}/pulls/{self.number}/files",
            max_retries=self.retries, label="GitHub PR files fetch")
        return [f["filename"] for f in files
                if f.get("filename") and not deterministic_review.should_skip_file(f["filename"])]

    def head_branch(self) -> str:
        pr = deterministic_review.with_retries(
            deterministic_review.github_api, "GET", f"/repos/{self.repo}/pulls/{self.number}",
            max_retries=self.retries, label="GitHub PR fetch")
        return pr["head"]["ref"]

    def post_comment(self, body: str) -> None:
        deterministic_review.with_retries(
            deterministic_review.github_api, "POST", f"/repos/{self.repo}/issues/{self.number}/comments",
            {"body": body}, max_retries=self.retries, label="GitHub PR comment post")


class GitLabAdapter:
    label = "MR"

    def __init__(self, retries: int):
        self.project_id = os.environ["CI_PROJECT_ID"]
        self.iid = os.environ["CI_MERGE_REQUEST_IID"]
        self.retries = retries

    def changed_files(self) -> list:
        changes = deterministic_review.with_retries(
            deterministic_review.gitlab_api, "GET",
            f"/projects/{self.project_id}/merge_requests/{self.iid}/changes",
            max_retries=self.retries, label="GitLab MR changes fetch")
        paths = [c.get("new_path", c.get("old_path")) for c in changes.get("changes", [])]
        return [p for p in paths if p and not deterministic_review.should_skip_file(p)]

    def head_branch(self) -> str:
        mr = deterministic_review.with_retries(
            deterministic_review.gitlab_api, "GET", f"/projects/{self.project_id}/merge_requests/{self.iid}",
            max_retries=self.retries, label="GitLab MR fetch")
        return mr["source_branch"]

    def post_comment(self, body: str) -> None:
        deterministic_review.with_retries(
            deterministic_review.gitlab_api, "POST",
            f"/projects/{self.project_id}/merge_requests/{self.iid}/notes",
            {"body": body}, max_retries=self.retries, label="GitLab MR comment post")


def _build_adapter(retries: int):
    source = deterministic_review.detect_ci_source()
    if source == "gitlab" or os.environ.get("CI_MERGE_REQUEST_IID"):
        return GitLabAdapter(retries)
    if source == "github" or os.environ.get("PR_NUMBER"):
        return GitHubAdapter(retries)
    print("ERROR: could not determine CI platform. Set GITHUB_REPOSITORY+PR_NUMBER "
          "(GitHub) or CI_PROJECT_ID+CI_MERGE_REQUEST_IID (GitLab), or CI_SOURCE explicitly.")
    sys.exit(1)


# ----------------------------------------------------------------------------
# Review (deterministic only -- no LLM)
# ----------------------------------------------------------------------------

def review_once(repo_root: str, changed: list, patterns: dict) -> list:
    """Review the CURRENT full content of the changed files. Deterministic
    only -- every finding comes from a skill's scripts/review.py via
    deterministic_review.py. Reviewing full file content (not the incremental
    diff) keeps the scope stable, so a real fix strictly reduces findings
    instead of inflating a diff.
    """
    det = []
    for path in changed:
        content = _read(repo_root, path)
        if content is None:
            continue
        print(f"  Reviewing (full content): {path}")
        det.extend(deterministic_review.analyze_file_content(content, path, patterns))
    return det


def run():
    repo_root = os.environ.get("REPO_ROOT", ".")
    provider = choose_provider()
    auto_fix = _env_bool("AUTO_FIX", False)
    max_iter = int(os.environ.get("MAX_FIX_ITERATIONS", "3"))
    threshold = int(os.environ.get("SCORE_THRESHOLD", "80"))
    api_retries = int(os.environ.get("API_MAX_RETRIES", "3"))

    adapter = _build_adapter(api_retries)
    resolved = dispatcher.resolve(repo_root)
    standard = resolved["standard"]  # fix-context only, never used to find issues
    patterns = deterministic_review.load_patterns(resolved["skills"], os.environ.get("SKILLS_DIR"))

    print(f"Platform: {adapter.label}")
    print(f"Frameworks detected -> skills: {', '.join(resolved['skills'])}")
    print(f"LLM provider (fix-only): {provider} | auto-fix: {auto_fix} | "
          f"threshold: {threshold} | max iterations (PR-level retry): {max_iter}")

    if provider == "none":
        print("NOTE: no LLM provider available -> auto-fix is DISABLED. Set "
              "ANTHROPIC_API_KEY (claude) or GH_MODELS_TOKEN/GITHUB_TOKEN (github) to enable it. "
              "Review findings are unaffected -- they never depend on the LLM.")
        if auto_fix:
            print("      auto-fix requested but no provider -> nothing to fix with.")
    print("-" * 60)

    branch = adapter.head_branch() if auto_fix else None
    changed = adapter.changed_files()

    iteration = 0
    det, score, verdict, report = [], 0, "Block", ""
    while True:
        label = "Initial review" if iteration == 0 else f"Re-review (iteration {iteration})"
        print(f"\n=== {label} ===")
        det = review_once(repo_root, changed, patterns)
        score, verdict = deterministic_review.compute_score(det)
        mode_label = f"{adapter.label} -- {label} -- skills: {', '.join(resolved['skills'])}"
        report = deterministic_review.format_report(
            det, score, verdict,
            {"mode_label": mode_label, "skills_label": ", ".join(resolved["skills"])})
        adapter.post_comment(report)
        print(f"Score: {score}/100 -- {verdict} | deterministic findings: {len(det)} "
              f"(Critical/High {_critical_high(det)})")

        if not auto_fix:
            break
        if score >= threshold:
            print(f"Score >= threshold ({threshold}); no fix needed.")
            break
        if iteration >= max_iter:
            print(f"Reached MAX_FIX_ITERATIONS ({max_iter}, PR-level retry cap); stopping.")
            break

        iteration += 1
        print(f"\n=== LLM fix (iteration {iteration}/{max_iter}) ===")
        fixes = llm_auto_fix.build_fixes(det, repo_root, standard, provider)
        accepted = apply_fixes_gated(fixes, repo_root, patterns)
        if not accepted:
            print("No fix improved the deterministic findings; stopping.")
            break
        if not llm_auto_fix.commit_and_push(accepted, repo_root, branch, iteration, max_retries=api_retries):
            print("Push failed after retries; stopping fix loop.")
            break

    deterministic_review.save_and_print_report(report, det, score, verdict)


if __name__ == "__main__":
    run()
