#!/usr/bin/env python3
"""
Agentic QA Code Review -- orchestrator entrypoint.

Ties the three layers together for a GitHub PR:

  1. Detect framework(s) and load the composed skill standard (dispatcher).
  2. Review the CURRENT full content of the changed files. Deterministic Layer 1
     (regex) is authoritative and drives the score + loop (reproducible, so
     counts move monotonically); Layer 2 (LLM) is advisory only. Post one comment.
  3. If AUTO_FIX and score < SCORE_THRESHOLD and iteration < MAX_FIX_ITERATIONS
     and the PR head was not authored by the bot:
       Layer 3 -- generate fixes, then a verify-before-commit gate accepts a
       fix ONLY if it does not regress the deterministic Critical/High count;
       commit accepted files as bot, push to the PR branch, re-review. The gate
       guarantees findings never increase across iterations.

Environment (GitHub):
  GITHUB_TOKEN, GITHUB_REPOSITORY (owner/repo), PR_NUMBER
  REPO_ROOT (checkout path, default '.')
Behaviour:
  LLM_PROVIDER    claude | github | none      (default none -> Layer 1 only)
  AUTO_FIX        true | false                (default false)
  MAX_FIX_ITERATIONS (default 3)
  SCORE_THRESHOLD (default 80)
  BOT_EMAIL / BOT_NAME  (fix commit identity + bot-author guard)
"""

import os
import sys

from pathlib import Path
from typing import Optional

import regex_review as rr
import detect_framework as dispatcher
from llm_review import llm_review_file
import llm_fix


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower().strip() in ("1", "true", "yes")


def apply_fixes_gated(fixes: list, repo_root: str) -> list:
    """Write a candidate fix only if it does NOT regress the file.

    Verify-before-commit: recompute deterministic Layer-1 findings on the
    candidate content. Accept only if Critical/High strictly drops, or holds
    while total drops. Any fix that would add a Critical/High (or make no
    progress) is rejected and the previous version is kept. This guarantees the
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
        old_f = rr.analyze_file_content(old, rel)
        new_f = rr.analyze_file_content(content, rel)
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


def advisory_section(advisory: list) -> str:
    """Render LLM findings as a clearly-labelled, NON-scoring advisory block."""
    if not advisory:
        return ""
    out = ("\n<details><summary>LLM advisory (semantic, non-scoring — "
           f"{len(advisory)} note(s))</summary>\n\n")
    for f in advisory:
        out += f"- **{f['severity']}** `{f['file']}:{f['line']}` — {f['rule']}\n"
    out += "\n</details>\n"
    return out


def fetch_pr_files(repo: str, pr_number: str) -> list:
    return rr.github_api("GET", f"/repos/{repo}/pulls/{pr_number}/files")


def fetch_pr_head_branch(repo: str, pr_number: str) -> str:
    pr = rr.github_api("GET", f"/repos/{repo}/pulls/{pr_number}")
    return pr["head"]["ref"]


def _read(repo_root: str, path: str) -> Optional[str]:
    fp = Path(repo_root) / path
    if not fp.is_file():
        return None
    return fp.read_text(encoding="utf-8", errors="ignore")


def _critical_high(findings: list) -> int:
    return sum(1 for f in findings if f["severity"] in ("Critical", "High"))


def changed_source_files(repo: str, pr_number: str) -> list:
    """Reviewable (non-skipped) files changed in the PR."""
    return [f["filename"] for f in fetch_pr_files(repo, pr_number)
            if f.get("filename") and not rr.should_skip_file(f["filename"])]


def review_once(repo_root: str, changed: list, standard: str, provider: str) -> tuple:
    """Review the CURRENT full content of the changed files.

    Deterministic Layer-1 (regex) is the authoritative signal that drives the
    score and the fix loop -- it is 100% reproducible, so counts move
    monotonically as fixes land. Layer-2 (LLM) is advisory only: it enriches the
    comment and adds fix hints, but never moves the headline score.
    Reviewing full file content (not the incremental diff) keeps the scope
    stable, so a real fix strictly reduces findings instead of inflating a diff.
    """
    det, advisory = [], []
    for path in changed:
        content = _read(repo_root, path)
        if content is None:
            continue
        print(f"  Reviewing (full content): {path}")
        det.extend(rr.analyze_file_content(content, path))          # Layer 1
        advisory.extend(llm_review_file(content, path, standard, provider))  # Layer 2
    return det, advisory


def post_comment(repo: str, pr_number: str, body: str) -> None:
    rr.github_api("POST", f"/repos/{repo}/issues/{pr_number}/comments", {"body": body})


def run():
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = os.environ["PR_NUMBER"]
    repo_root = os.environ.get("REPO_ROOT", ".")
    provider = os.environ.get("LLM_PROVIDER", "none").lower().strip()
    auto_fix = _env_bool("AUTO_FIX", False)
    max_iter = int(os.environ.get("MAX_FIX_ITERATIONS", "3"))
    threshold = int(os.environ.get("SCORE_THRESHOLD", "80"))

    resolved = dispatcher.resolve(repo_root)
    standard = resolved["standard"]
    print(f"Repo: {repo}  PR: #{pr_number}")
    print(f"Frameworks detected -> skills: {', '.join(resolved['skills'])}")
    print(f"LLM provider: {provider} | auto-fix: {auto_fix} | "
          f"threshold: {threshold} | max iterations: {max_iter}")

    # Make the common misconfiguration loud: without an LLM provider the agent
    # can only run Layer 1 (regex) -- it will comment but never LLM-review or fix.
    if provider == "none":
        print("NOTE: LLM_PROVIDER=none -> Layer 2 (LLM review) and Layer 3 (LLM "
              "fix) are DISABLED. Set LLM_PROVIDER=claude (ANTHROPIC_API_KEY) or "
              "LLM_PROVIDER=github (GH_MODELS_TOKEN) to enable them.")
        if auto_fix:
            print("      auto-fix requested but no provider -> nothing to fix with.")
    print("-" * 60)

    # Bot-author guard: never start a fix loop off the bot's own push.
    if auto_fix and llm_fix.last_commit_is_bot(repo_root):
        print("PR head was authored by the bot -- skipping auto-fix to avoid a loop.")
        auto_fix = False

    branch = fetch_pr_head_branch(repo, pr_number) if auto_fix else None
    changed = changed_source_files(repo, pr_number)

    iteration = 0
    while True:
        label = "Initial review" if iteration == 0 else f"Re-review (iteration {iteration})"
        print(f"\n=== {label} ===")
        # Deterministic Layer-1 is authoritative; LLM is advisory only.
        det, advisory = review_once(repo_root, changed, standard, provider)
        score, verdict = rr.compute_score(det)
        mode_label = f"PR #{pr_number} -- {label} -- skills: {', '.join(resolved['skills'])}"
        report = rr.format_report(det, score, verdict, {"mode_label": mode_label})
        report += advisory_section(advisory)
        post_comment(repo, pr_number, report)
        print(f"Score: {score}/100 -- {verdict} | deterministic findings: {len(det)} "
              f"(Critical/High {_critical_high(det)}) | advisory: {len(advisory)}")

        if not auto_fix:
            break
        if score >= threshold:
            print(f"Score >= threshold ({threshold}); no fix needed.")
            break
        if iteration >= max_iter:
            print(f"Reached MAX_FIX_ITERATIONS ({max_iter}); stopping.")
            break

        iteration += 1
        print(f"\n=== Layer 3: auto-fix (iteration {iteration}) ===")
        # Target deterministic findings (authoritative) plus advisory hints.
        fixes = llm_fix.build_fixes(det + advisory, repo_root, standard, provider)
        accepted = apply_fixes_gated(fixes, repo_root)   # verify-before-commit gate
        if not accepted:
            print("No fix improved the deterministic findings; stopping.")
            break
        if not llm_fix.commit_and_push(accepted, repo_root, branch, iteration):
            print("Push failed; stopping fix loop.")
            break

    # Save the last report + set exit status for CI gating (uses deterministic findings).
    rr.save_and_print_report(report, det, score, verdict)


if __name__ == "__main__":
    source = rr.detect_ci_source()
    if source != "github" and not os.environ.get("GITHUB_REPOSITORY"):
        print("agent.py currently orchestrates GitHub PRs. "
              "Set GITHUB_REPOSITORY + PR_NUMBER, or use review_runner.py for GitLab.")
        sys.exit(1)
    run()
